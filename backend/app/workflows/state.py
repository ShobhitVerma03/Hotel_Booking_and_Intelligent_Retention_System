"""Typed state for the deterministic Phase 8 retention graph."""

from typing import NotRequired, TypedDict


class RetentionWorkflowState(TypedDict, total=False):
    request_id: int
    booking_id: int
    customer_id: int
    booking_context: dict
    customer_context: dict
    risk_score: float | None
    risk_category: str | None
    policy_results: list[dict]
    policy_context: str
    recommendation: dict | None
    recommendation_reason: str | None
    proposed_offer: dict | None
    # Added by the Phase 9 manager-only finalisation service.  This is workflow
    # state, not a substitute for the audited relational decision record.
    manager_decision: dict | None
    workflow_status: str
    error: NotRequired[str | None]
