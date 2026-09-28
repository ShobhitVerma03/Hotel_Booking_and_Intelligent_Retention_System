# Phase 10: Multilingual Natural-Language Analytics

NL→SQL is a manager-only, read-only analytics capability. It has no authority
to modify hotel business state or make retention decisions.

## Flow

`question → language metadata → optional multilingual LLM/local planner → SQL AST validator → bounded read-only execution → structured results → audit`

The only supported input-language metadata values are English (`en`), Hindi
(`hi`), Hinglish (`hinglish`), Gujarati/Rajasthani (`gu_rj`), and Telugu
(`te`). Tamil is intentionally not supported. Detection is convenience
metadata only; it is never an authorization or security control.

## Security model

The LLM never receives database access and never executes SQL. Every candidate
is parsed with `sqlglot`; exactly one SELECT is required. Comments, stacked
statements, writes, DDL, non-allowlisted tables/columns, wildcard extraction,
unsafe functions, literals used as filters, and LLM-controlled limits are
rejected. The service applies `NL_SQL_MAX_ROWS` as a named parameter.

Only selected analytics fields from `customers`, `rooms`, `bookings`, `offers`,
`retention_requests`, and `retention_decisions` are allowlisted. `users`,
password hashes, secrets, policy files, Chroma data, and LangGraph checkpoints
are unavailable. PostgreSQL deployments should use a database role with
read-only permission; local SQLite relies on application-level AST enforcement.

## Configuration

`NL_SQL_ENABLED`, `NL_SQL_MAX_ROWS`, and `NL_SQL_TIMEOUT_SECONDS` control the
feature. `NL_SQL_LLM_ENABLED` enables the existing `GROQ_API_KEY` path via
`NL_SQL_LLM_MODEL`; when disabled, the limited offline planner supports safe
development/demo intents and asks for clarification when it cannot interpret a
question safely.

## API

`POST /api/v1/admin/nl-sql/query` accepts `{ "question": "..." }` and returns
language metadata, intent, validated SQL, columns, rows, row count, and an
explanation. A manager JWT is required. Successful and rejected requests are
audited without tokens, credentials, or secrets.
