"""Manager-only multilingual natural-language analytics with secure SQL execution.

Language understanding is deliberately separate from SQL security. Whether a
candidate comes from the optional Groq LLM or the offline local planner, it is
always parsed by sqlglot, checked against this module's schema allowlist, and
executed only as a bounded SELECT.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from backend.app.core.config import get_settings
from backend.app.services.audit import log_event


class NLAnalyticsError(RuntimeError):
    status_code = 422


class ClarificationRequired(NLAnalyticsError):
    """The question has no safe, deterministic analytics interpretation."""


class SQLValidationError(NLAnalyticsError):
    """Candidate SQL failed the security boundary and will never execute."""


class AnalyticsUnavailable(NLAnalyticsError):
    status_code = 503


# This is deliberately narrower than the ORM schema. It excludes users,
# password hashes, credentials, and application/vector/checkpoint internals.
SCHEMA_ALLOWLIST: dict[str, set[str]] = {
    "customers": {"customer_id", "name", "email", "phone", "loyalty_tier", "created_at"},
    "rooms": {"room_id", "room_number", "room_type", "price_per_night", "capacity", "status", "created_at"},
    "bookings": {"booking_id", "customer_id", "room_id", "check_in", "check_out", "guests", "total_amount", "status", "created_at"},
    "offers": {"offer_id", "customer_id", "booking_id", "offer_type", "discount", "description", "source", "status", "created_at"},
    "retention_requests": {"request_id", "booking_id", "customer_id", "risk_score", "risk_level", "status", "reason", "created_at"},
    "retention_decisions": {"decision_id", "request_id", "manager_id", "action", "reason", "created_at"},
}

SUPPORTED_LANGUAGES = {"en", "hi", "hinglish", "gu_rj", "te"}
_SAFE_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE"}
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|MERGE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CandidateQuery:
    intent: str
    sql: str
    parameters: dict[str, Any]
    explanation: str


def detect_language(question: str) -> str:
    """Best-effort metadata only; it is never used as an authorization control."""

    if re.search(r"[\u0b80-\u0bff]", question):
        # Tamil is intentionally unsupported in Phase 10. This internal value
        # is used only to return clarification, never as supported metadata.
        return "unsupported"
    if re.search(r"[\u0c00-\u0c7f]", question):
        return "te"
    if re.search(r"[\u0a80-\u0aff]", question):
        return "gu_rj"
    if re.search(r"[\u0900-\u097f]", question):
        return "hi"
    words = set(re.findall(r"[a-z]+", question.lower()))
    if words & {"dikhao", "dikha", "saare", "kitni", "hui", "hain", "jin", "zyada", "kar", "karo", "mathi", "ketli", "thai", "batao"}:
        return "hinglish" if not words & {"mathi", "ketli", "thai"} else "gu_rj"
    return "en"


def _number_from_question(question: str) -> int | None:
    match = re.search(r"\b(\d+)\b", question)
    if match:
        return int(match.group(1))
    normalized = question.lower()
    word_numbers = {
        "one": 1, "two": 2, "twice": 2, "three": 3, "do": 2, "teen": 3,
        "दो": 2, "तीन": 3, "બે": 2, "ત્રણ": 3,
        "\u0c30\u0c46\u0c02\u0c21\u0c41": 2,  # Telugu: రెండు
        "\u0c2e\u0c42\u0c21\u0c41": 3,  # Telugu: మూడు
    }
    return next((value for word, value in word_numbers.items() if word in normalized), None)


class LocalIntentPlanner:
    """Small offline planner for development, demos and deterministic tests.

    It handles supported-language cancellation/count intents but returns a
    clarification for anything it cannot map safely. It is one planner and one
    SQL pipeline—not one SQL generator per language.
    """

    def generate(self, question: str, language: str) -> CandidateQuery:
        if language not in SUPPORTED_LANGUAGES:
            raise ClarificationRequired("This input language is not supported for analytics. Please use English, Hindi, Hinglish, Gujarati/Rajasthani, or Telugu.")
        lowered = question.lower()
        # Neither customers nor bookings currently has a city/location field.
        # Returning a clarification avoids inventing a schema mapping.
        if any(city in lowered for city in ("mumbai", "delhi", "bengaluru", "bangalore", "hyderabad", "chennai", "jaipur", "udaipur", "goa", "pune", "kolkata", "gurugram", "noida", "lucknow", "chandigarh")):
            raise ClarificationRequired("Location analytics are unavailable because the current platform schema does not store customer or booking city.")
        cancellation_terms = ("cancel", "cancellation", "रद्द", "कैंसल", "રદ", "કૅન્સલ", "రద్ద", "క్యాన్స")
        booking_terms = ("booking", "bookings", "बुकिंग", "બુકિંગ", "బుకింగ్")
        if any(term in lowered for term in cancellation_terms):
            minimum = _number_from_question(question)
            if minimum is None:
                raise ClarificationRequired("Please specify how many cancellations to analyse.")
            return CandidateQuery(
                intent="customers with cancellations above a threshold",
                sql=(
                    "SELECT c.customer_id, c.name, c.email, COUNT(b.booking_id) AS cancellation_count "
                    "FROM customers AS c JOIN bookings AS b ON b.customer_id = c.customer_id "
                    "WHERE b.status = :cancelled_status "
                    "GROUP BY c.customer_id, c.name, c.email "
                    "HAVING COUNT(b.booking_id) > :minimum_cancellations "
                    "ORDER BY cancellation_count DESC"
                ),
                # SQLAlchemy persists the current enum name in the existing
                # schema. Keep the stored value unchanged and parameterized.
                parameters={"cancelled_status": "CANCELLED", "minimum_cancellations": minimum},
                explanation="Lists customers whose cancelled-booking count exceeds the requested threshold.",
            )
        if any(term in lowered for term in booking_terms) and any(term in lowered for term in ("how many", "count", "kitni", "ketli", "कितनी", "કેટલી", "ఎన్ని")):
            return CandidateQuery(
                intent="total booking count",
                sql="SELECT COUNT(b.booking_id) AS booking_count FROM bookings AS b",
                parameters={},
                explanation="Counts bookings in the hotel platform database.",
            )
        if "customer" in lowered or "customers" in lowered or "customers" in question:
            return CandidateQuery(
                intent="customer list",
                sql="SELECT c.customer_id, c.name, c.email, c.loyalty_tier FROM customers AS c ORDER BY c.created_at DESC",
                parameters={},
                explanation="Lists customers using the approved analytics fields.",
            )
        raise ClarificationRequired("Please clarify the analytics question using supported hotel business data.")


class GroqIntentPlanner:
    """Optional multilingual structured-output planner using existing GROQ_API_KEY."""

    def generate(self, question: str, language: str) -> CandidateQuery:
        settings = get_settings()
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:  # pragma: no cover - deployment setup failure
            raise AnalyticsUnavailable("The configured SQL generation provider is unavailable") from exc
        schema_text = "; ".join(f"{table}({', '.join(sorted(columns))})" for table, columns in SCHEMA_ALLOWLIST.items())
        prompt = (
            "Return JSON only with intent, sql, parameters, explanation. Understand the question directly in English, Hindi, Hinglish, Gujarati/Rajasthani, or Telugu. "
            "Use SQLite-compatible SELECT only, named parameters for EVERY value including numbers and enum values, no SQL literals, no LIMIT, no semicolon, and no comments. "
            "For example, use HAVING COUNT(b.booking_id) > :minimum_cancellations with parameters {\"minimum_cancellations\": 2}; use b.status = :cancelled_status with parameters {\"cancelled_status\": \"CANCELLED\"}. "
            "The existing Booking status values are enum names such as CANCELLED, CONFIRMED, and CANCEL_PENDING. "
            "Use only this allowlist: "
            f"{schema_text}. SQL cannot access users, secrets, configuration, files, vectors, policy documents, or checkpoints. "
            f"Question language metadata is {language}. Question: {question}"
        )
        try:
            if not settings.groq_api_key:
                raise AnalyticsUnavailable("The SQL generation provider is not configured")
            response = ChatGroq(model=settings.nl_sql_llm_model, temperature=0, api_key=settings.groq_api_key).invoke(prompt)
            payload = json.loads(str(response.content))
            sql = str(payload["sql"]).strip()
            if sql.startswith("```") and sql.endswith("```"):
                sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
            # A lone terminal delimiter is formatting, not a stacked query.
            # The AST validator still rejects any embedded delimiter/comments.
            if sql.endswith(";") and sql.count(";") == 1:
                sql = sql[:-1].rstrip()
            return CandidateQuery(
                intent=str(payload["intent"]), sql=sql,
                parameters=dict(payload.get("parameters") or {}), explanation=str(payload["explanation"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ClarificationRequired("The analytics question could not be safely interpreted. Please rephrase it.") from exc
        except Exception as exc:  # pragma: no cover - external provider failure
            raise AnalyticsUnavailable("SQL generation is temporarily unavailable") from exc


class SQLAstValidator:
    """The actual security boundary for all generated candidate SQL."""

    def __init__(self, max_rows: int) -> None:
        self.max_rows = max_rows

    def validate(self, candidate: CandidateQuery) -> tuple[str, dict[str, Any]]:
        sql = candidate.sql.strip()
        if not sql or ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
            raise SQLValidationError("SQL comments and multiple statements are not allowed")
        if _FORBIDDEN_KEYWORDS.search(sql):
            raise SQLValidationError("Only read-only SELECT analytics are allowed")
        try:
            statements = parse(sql, read="sqlite")
        except ParseError as exc:
            raise SQLValidationError("Generated SQL could not be parsed") from exc
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise SQLValidationError("Exactly one SELECT statement is required")
        statement = statements[0]
        if isinstance(statement, exp.Select) and not statement.expressions:
            raise SQLValidationError("Generated SQL must select at least one approved field")
        if statement.args.get("limit") is not None:
            raise SQLValidationError("The service applies the result limit; generated SQL must not set LIMIT")
        self._validate_tables_and_columns(statement)
        self._validate_expression_safety(statement)
        placeholders = {str(item.this) for item in statement.find_all(exp.Placeholder)}
        if placeholders != set(candidate.parameters):
            raise SQLValidationError("SQL parameters do not match the validated parameter payload")
        for key, value in candidate.parameters.items():
            if not isinstance(key, str) or not isinstance(value, (str, int, float, bool, type(None), date, datetime)):
                raise SQLValidationError("SQL parameters must be scalar values")
            if isinstance(value, str) and len(value) > 500:
                raise SQLValidationError("SQL parameter value is too long")
        # The service, not the LLM, owns the hard result cap.
        return f"{statement.sql(dialect='sqlite')} LIMIT :_nl_sql_limit", {**candidate.parameters, "_nl_sql_limit": self.max_rows}

    def _validate_tables_and_columns(self, statement: exp.Expression) -> None:
        aliases: dict[str, str] = {}
        for table in statement.find_all(exp.Table):
            name = table.name.lower()
            if name not in SCHEMA_ALLOWLIST or table.catalog or table.db:
                raise SQLValidationError("Generated SQL references a table outside the analytics allowlist")
            aliases[table.alias_or_name.lower()] = name
        if not aliases:
            raise SQLValidationError("Analytics SQL must reference an approved business table")
        selected_aliases = {
            projection.alias.lower() for projection in statement.expressions
            if isinstance(projection, exp.Alias) and projection.alias
        }
        for column in statement.find_all(exp.Column):
            name = column.name.lower()
            qualifier = column.table.lower() if column.table else ""
            if not qualifier and name in selected_aliases:
                # ORDER BY an aggregate alias, e.g. cancellation_count, refers
                # to an already validated SELECT expression rather than a table.
                continue
            if qualifier:
                table = aliases.get(qualifier)
                if not table or name not in SCHEMA_ALLOWLIST[table]:
                    raise SQLValidationError("Generated SQL references a column outside the analytics allowlist")
            elif not any(name in columns for columns in SCHEMA_ALLOWLIST.values()):
                raise SQLValidationError("Generated SQL references a column outside the analytics allowlist")

    def _validate_expression_safety(self, statement: exp.Expression) -> None:
        forbidden_types = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter)
        if any(isinstance(node, forbidden_types) for node in statement.walk()):
            raise SQLValidationError("Only read-only SELECT analytics are allowed")
        for star in statement.find_all(exp.Star):
            if not isinstance(star.parent, exp.Count):
                raise SQLValidationError("Wildcard column selection is not allowed")
        for func in statement.find_all(exp.Func):
            if func.sql_name().upper() not in _SAFE_FUNCTIONS:
                raise SQLValidationError("Generated SQL uses a function outside the analytics allowlist")
        # Literal filters could be concatenated from user input. Values must be
        # named parameters; numeric literals inside expressions are disallowed too.
        if any(True for _ in statement.find_all(exp.Literal)):
            raise SQLValidationError("Filter values must use named parameters")


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _audit_question(question: str) -> str:
    # Do not turn audit logs into a place where an operator can accidentally
    # submit a password/token/API key for storage.
    if re.search(r"password|token|api[_ -]?key|secret", question, re.IGNORECASE):
        return "[redacted potentially sensitive analytics question]"
    return question


class NLAnalyticsService:
    def __init__(self, db: Session, manager_id: int) -> None:
        self.db = db
        self.manager_id = manager_id
        self.settings = get_settings()

    def _planner(self):
        return GroqIntentPlanner() if self.settings.nl_sql_llm_enabled else LocalIntentPlanner()

    def query(self, question: str) -> dict[str, Any]:
        if not self.settings.nl_sql_enabled:
            raise AnalyticsUnavailable("NL-to-SQL analytics are disabled")
        language = detect_language(question)
        try:
            candidate = self._planner().generate(question, language)
            sql, parameters = SQLAstValidator(self.settings.nl_sql_max_rows).validate(candidate)
            columns, rows = self._execute_read_only(sql, parameters)
        except NLAnalyticsError as exc:
            self._audit(question, language, "rejected", str(exc))
            raise
        except Exception as exc:  # pragma: no cover - DB driver/runtime failure
            self._audit(question, language, "failed", "Analytics execution failed")
            raise AnalyticsUnavailable("Analytics execution is temporarily unavailable") from exc
        result = {
            "question": question, "language": language, "intent": candidate.intent,
            "sql": sql, "columns": columns, "rows": rows, "row_count": len(rows),
            "explanation": candidate.explanation,
        }
        self._audit(question, language, "executed", None, sql=sql, row_count=len(rows))
        return result

    def _execute_read_only(self, sql: str, parameters: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        # The AST gate permits only SELECT. PostgreSQL deployments should supply
        # a DB role with read-only privileges; SQLite relies on this gate because
        # it has no per-connection application role model.
        bind = self.db.get_bind()
        connection: Connection = bind.connect()
        raw_sqlite_connection = None
        try:
            if bind.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
                # PostgreSQL does not permit a bound parameter in SET LOCAL
                # (psycopg renders it as ``$1``).  set_config keeps the
                # timeout parameterized and local to this read-only
                # transaction.
                connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                    {"timeout_ms": str(self.settings.nl_sql_timeout_seconds * 1000)},
                )
            elif bind.dialect.name == "sqlite":
                # SQLite has no server-side statement timeout. Its progress
                # handler aborts a long-running read without enabling writes.
                raw_sqlite_connection = getattr(connection.connection, "driver_connection", connection.connection)
                deadline = time.monotonic() + self.settings.nl_sql_timeout_seconds
                raw_sqlite_connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
            result = connection.execute(text(sql), parameters)
            columns = list(result.keys())
            rows = [{key: _json_value(value) for key, value in row._mapping.items()} for row in result.fetchmany(self.settings.nl_sql_max_rows)]
            return columns, rows
        finally:
            if raw_sqlite_connection is not None:
                raw_sqlite_connection.set_progress_handler(None, 0)
            connection.close()

    def _audit(self, question: str, language: str, outcome: str, reason: str | None, sql: str | None = None, row_count: int | None = None) -> None:
        details = {"question": _audit_question(question), "language": language, "outcome": outcome}
        if reason:
            details["reason"] = reason
        if sql:
            details["sql"] = sql
        if row_count is not None:
            details["row_count"] = row_count
        log_event(self.db, "analytics.nl_sql", "analytics_query", "manager", details, self.manager_id)
        self.db.commit()
