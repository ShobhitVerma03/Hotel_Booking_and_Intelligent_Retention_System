"""Explicit, checkpointed retention-recommendation workflow.

Phase 8 deliberately stops at ``AWAITING_MANAGER``.  It reads business data,
ML risk and policy context, then creates a structured recommendation.  It does
not approve/reject a request, create an offer, or update a booking.
"""

from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import Customer, RetentionRequest
from backend.app.services.audit import log_event
from backend.app.services.rag import PolicyRAGService, RAGError
from backend.app.schemas.workflow import RetentionRecommendation
from backend.app.workflows.state import RetentionWorkflowState
from backend.ml.features import customer_features
from backend.ml.predict import predict


class WorkflowStatus:
    STARTED = "STARTED"
    CONTEXT_LOADED = "CONTEXT_LOADED"
    RISK_EVALUATED = "RISK_EVALUATED"
    POLICY_RETRIEVED = "POLICY_RETRIEVED"
    RECOMMENDATION_READY = "RECOMMENDATION_READY"
    AWAITING_MANAGER = "AWAITING_MANAGER"
    MANAGER_APPROVED = "MANAGER_APPROVED"
    MANAGER_MODIFIED = "MANAGER_MODIFIED"
    MANAGER_REJECTED = "MANAGER_REJECTED"
    FAILED = "FAILED"


class RetentionWorkflowError(RuntimeError):
    """Raised only for configuration/checkpoint failures outside graph nodes."""


@lru_cache(maxsize=4)
def get_retention_checkpointer(path: str) -> SqliteSaver:
    """One persistent local checkpointer per configured storage location."""

    checkpoint_path = Path(path)
    try:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteSaver(sqlite3.connect(str(checkpoint_path), check_same_thread=False))
    except Exception as exc:  # pragma: no cover - platform configuration failure
        raise RetentionWorkflowError("LangGraph checkpoint storage is unavailable") from exc


def _sources(results: list[dict]) -> list[dict]:
    """Keep only provenance needed by the recommendation/API response."""

    seen: set[str] = set()
    sources: list[dict] = []
    for result in results:
        chunk_id = str(result["chunk_id"])
        if chunk_id not in seen:
            sources.append({"source": str(result["source"]), "page": int(result["page"]), "chunk_id": chunk_id})
            seen.add(chunk_id)
    return sources


def _policy_discount_limit(policy_context: str) -> float | None:
    """Extract only a rate limit explicitly stated in retrieved policy text."""

    match = re.search(r"room\s+rate\s+discount\s+up\s+to\s+(\d+(?:\.\d+)?)\s*%", policy_context, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _policy_low_risk_future_voucher_limit(policy_context: str) -> float | None:
    """Read a low-risk *future-stay* voucher limit from retrieved policy text.

    This deliberately differs from a current-booking room-rate discount.  The
    policy allows the former for low-risk guests and prohibits the latter.
    """

    match = re.search(
        # PDF extraction may retain a bullet between the label and the
        # percentage.  Accept only non-numeric formatting characters there;
        # the percentage and the "discount voucher" wording still must come
        # from retrieved policy text.
        r"future\s*-?\s*stay\s+incentive\s*:\s*(?:[^\d]{0,80}?)(\d+(?:\.\d+)?)\s*%\s*discount\s+voucher",
        policy_context,
        flags=re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _recommendation(state: RetentionWorkflowState) -> dict:
    risk = state.get("risk_category") or "UNKNOWN"
    sources = _sources(state.get("policy_results", []))
    policy_context = state.get("policy_context", "")

    if risk == "UNKNOWN":
        payload = {
            "action": "manager_review_without_ml_risk",
            "offer_type": None,
            "discount_percentage": None,
            "reason": "ML risk is unavailable because the customer has insufficient historical booking data. No ML-based discount is proposed.",
            "risk_category": risk,
            "policy_sources": sources,
            "requires_manager_review": True,
            "policy_limit_percentage": None,
            "policy_conflict": False,
        }
    elif risk == "HIGH":
        limit = _policy_discount_limit(policy_context)
        if limit is None:
            payload = {
                "action": "policy_review_required",
                "offer_type": None,
                "discount_percentage": None,
                "reason": "Retrieved policy context did not establish an enforceable current-booking rate-discount limit; manager review is required.",
                "risk_category": risk,
                "policy_sources": sources,
                "requires_manager_review": True,
                "policy_limit_percentage": None,
                "policy_conflict": True,
            }
        else:
            payload = {
                "action": "propose_standard_high_risk_retention",
                "offer_type": "room_rate_discount",
                "discount_percentage": limit,
                "reason": "The proposed rate discount is capped at the limit explicitly found in the retrieved high-risk policy context.",
                "risk_category": risk,
                "policy_sources": sources,
                "requires_manager_review": True,
                "policy_limit_percentage": limit,
                "policy_conflict": False,
            }
    elif risk == "MEDIUM":
        payload = {
            "action": "propose_medium_risk_experience_benefit",
            "offer_type": "experience_benefit_review",
            "discount_percentage": None,
            "reason": "Retrieved medium-risk policy context supports service or experience benefits; this workflow does not issue an offer.",
            "risk_category": risk,
            "policy_sources": sources,
            "requires_manager_review": True,
            "policy_limit_percentage": None,
            "policy_conflict": False,
        }
    else:
        voucher_limit = _policy_low_risk_future_voucher_limit(policy_context)
        if voucher_limit is not None:
            payload = {
                "action": "propose_low_risk_future_stay_voucher",
                "offer_type": "future_stay_discount_voucher",
                "discount_percentage": voucher_limit,
                "reason": "Retrieved low-risk policy permits a future-stay discount voucher. This is not a discount on the current booking.",
                "risk_category": risk,
                "policy_sources": sources,
                "requires_manager_review": True,
                "policy_limit_percentage": voucher_limit,
                "policy_conflict": False,
            }
        else:
            payload = {
                "action": "propose_low_risk_relationship_building",
                "offer_type": "relationship_building",
                "discount_percentage": None,
                "reason": "Retrieved low-risk policy supports relationship-building actions but did not return an enforceable offer limit. Manager review remains required.",
                "risk_category": risk,
                "policy_sources": sources,
                "requires_manager_review": True,
                "policy_limit_percentage": None,
                "policy_conflict": False,
            }
    # Pydantic validation prevents malformed recommendations from entering state.
    return RetentionRecommendation.model_validate(payload).model_dump()


def build_retention_graph(db: Session, checkpointer: SqliteSaver):
    """Build a graph whose closures use the request-scoped SQLAlchemy session."""

    def load_context(state: RetentionWorkflowState) -> dict:
        request = db.get(RetentionRequest, state["request_id"])
        if not request or not request.booking or not request.customer:
            return {"workflow_status": WorkflowStatus.FAILED, "error": "Retention request, booking, or customer context was not found"}
        booking = request.booking
        customer = request.customer
        history = list(customer.bookings)
        return {
            "booking_id": booking.booking_id,
            "customer_id": customer.customer_id,
            "booking_context": {
                "booking_id": booking.booking_id,
                "room_id": booking.room_id,
                "room_type": booking.room.room_type,
                "check_in": booking.check_in.isoformat(),
                "check_out": booking.check_out.isoformat(),
                "guests": booking.guests,
                "total_amount": float(booking.total_amount),
                "status": booking.status.value,
                "cancellation_reason": request.reason,
            },
            "customer_context": {
                "customer_id": customer.customer_id,
                "loyalty_tier": customer.loyalty_tier,
                "booking_count": len(history),
                "completed_stays": sum(item.status.value == "completed" for item in history),
                "previous_cancellations": sum(item.status.value == "cancelled" for item in history),
            },
            "workflow_status": WorkflowStatus.CONTEXT_LOADED,
            "error": None,
        }

    def evaluate_risk(state: RetentionWorkflowState) -> dict:
        try:
            customer = db.get(Customer, state["customer_id"])
            if not customer:
                raise RetentionWorkflowError("Customer context was not found")
            output = predict(customer_features(db, customer))
            return {
                "risk_score": output["risk_score"],
                "risk_category": output["risk_category"],
                "workflow_status": WorkflowStatus.RISK_EVALUATED,
            }
        except Exception:
            return {"workflow_status": WorkflowStatus.FAILED, "error": "ML risk prediction is unavailable"}

    def retrieve_policy(state: RetentionWorkflowState) -> dict:
        try:
            booking = state["booking_context"]
            risk = state.get("risk_category") or "UNKNOWN"
            topic = {
                "LOW": "low-risk permitted future-stay voucher, welcome amenity, and current-booking discount prohibition",
                "MEDIUM": "medium-risk permitted reassurance and experience benefits",
                "HIGH": "high-risk permitted room-rate discount limit and targeted intervention",
            }.get(risk, "permitted retention actions when ML risk is unavailable")
            query = (
                f"Retention policy for a {risk} cancellation-risk guest. Find {topic}. "
                f"Current booking is {booking['room_type']} with value {booking['total_amount']}."
            )
            # A policy section can span adjacent page-aware chunks.  Retain the
            # configured retrieval baseline, but ask for enough context for the
            # workflow to evaluate both the permission and its constraint (for
            # example, the low-risk future-stay incentive and the prohibition on
            # a current-booking discount).  This remains semantic RAG retrieval;
            # no policy amount is supplied by the workflow itself.
            policy_top_k = min(10, max(5, get_settings().rag_top_k))
            results = PolicyRAGService().retrieve_policy(query, top_k=policy_top_k)
            if not results:
                raise RAGError("No policy context was retrieved")
            return {
                "policy_results": results,
                "policy_context": "\n\n".join(row["text"] for row in results),
                "workflow_status": WorkflowStatus.POLICY_RETRIEVED,
            }
        except Exception:
            return {"workflow_status": WorkflowStatus.FAILED, "error": "Policy retrieval is unavailable"}

    def generate_recommendation(state: RetentionWorkflowState) -> dict:
        try:
            recommendation = _recommendation(state)
            return {
                "recommendation": recommendation,
                "recommendation_reason": recommendation["reason"],
                "proposed_offer": {key: recommendation[key] for key in ("offer_type", "discount_percentage")},
                "workflow_status": WorkflowStatus.AWAITING_MANAGER,
            }
        except Exception:
            return {"workflow_status": WorkflowStatus.FAILED, "error": "Recommendation could not be validated against policy"}

    def continue_or_end(state: RetentionWorkflowState) -> Literal["risk", "policy", "recommendation", "end"]:
        status = state.get("workflow_status")
        if status == WorkflowStatus.CONTEXT_LOADED:
            return "risk"
        if status == WorkflowStatus.RISK_EVALUATED:
            return "policy"
        if status == WorkflowStatus.POLICY_RETRIEVED:
            return "recommendation"
        return "end"

    graph = StateGraph(RetentionWorkflowState)
    graph.add_node("load_context", load_context)
    graph.add_node("evaluate_risk", evaluate_risk)
    graph.add_node("retrieve_policy", retrieve_policy)
    graph.add_node("generate_recommendation", generate_recommendation)
    graph.add_edge(START, "load_context")
    graph.add_conditional_edges("load_context", continue_or_end, {"risk": "evaluate_risk", "end": END})
    graph.add_conditional_edges("evaluate_risk", continue_or_end, {"policy": "retrieve_policy", "end": END})
    graph.add_conditional_edges("retrieve_policy", continue_or_end, {"recommendation": "generate_recommendation", "end": END})
    graph.add_edge("generate_recommendation", END)
    return graph.compile(checkpointer=checkpointer)


class RetentionWorkflowService:
    """Runs or resumes a request-specific workflow without mutating business state."""

    def __init__(self, db: Session, manager_id: int | None = None) -> None:
        self.db = db
        self.manager_id = manager_id
        self.checkpointer = get_retention_checkpointer(get_settings().langgraph_checkpoint_path)
        self.graph = build_retention_graph(db, self.checkpointer)

    def run(self, request_id: int) -> dict:
        config = {"configurable": {"thread_id": f"retention-request-{request_id}"}}
        try:
            snapshot = self.graph.get_state(config)
            if snapshot.values and snapshot.values.get("workflow_status") in {
                WorkflowStatus.AWAITING_MANAGER,
                WorkflowStatus.MANAGER_APPROVED,
                WorkflowStatus.MANAGER_MODIFIED,
                WorkflowStatus.MANAGER_REJECTED,
            }:
                return dict(snapshot.values)
            result = self.graph.invoke({"request_id": request_id, "workflow_status": WorkflowStatus.STARTED}, config)
        except Exception as exc:  # pragma: no cover - checkpointer runtime failure
            raise RetentionWorkflowError("Retention workflow checkpoint execution failed") from exc

        if result.get("workflow_status") == WorkflowStatus.AWAITING_MANAGER:
            # Audits the preparation event only—not a manager decision or offer.
            log_event(
                self.db,
                "retention.workflow_recommendation_generated",
                "retention_request",
                request_id,
                {"risk_category": result.get("risk_category"), "workflow_status": result.get("workflow_status")},
                self.manager_id,
            )
            self.db.commit()
        return dict(result)

    def state(self, request_id: int) -> dict:
        """Return the persisted workflow snapshot for a request, if present."""

        config = {"configurable": {"thread_id": f"retention-request-{request_id}"}}
        try:
            return dict(self.graph.get_state(config).values or {})
        except Exception as exc:  # pragma: no cover - checkpointer runtime failure
            raise RetentionWorkflowError("Retention workflow checkpoint execution failed") from exc

    def record_manager_decision(self, request_id: int, status: str, decision: dict) -> None:
        """Persist terminal manager workflow context alongside relational audit data."""

        config = {"configurable": {"thread_id": f"retention-request-{request_id}"}}
        try:
            self.graph.update_state(config, {"workflow_status": status, "manager_decision": decision})
        except Exception as exc:  # pragma: no cover - checkpointer runtime failure
            raise RetentionWorkflowError("Retention workflow checkpoint execution failed") from exc
