"""Persistent, manager-only Phase 9 retention decision service.

This module deliberately finalises only the hotel manager's side of the
workflow.  It never cancels a booking or records a customer response.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.entities import Offer, RetentionDecision, RetentionRequest, User
from backend.app.models.enums import BookingStatus, DecisionAction, OfferStatus, RetentionRequestStatus
from backend.app.schemas.retention import ManagerDecisionAction, ManagerDecisionCreate
from backend.app.services.audit import log_event
from backend.app.workflows.retention import RetentionWorkflowError, RetentionWorkflowService, WorkflowStatus


class RetentionDecisionError(HTTPException):
    """A controlled conflict when a manager decision cannot be safely finalised."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


_TERMINAL_REQUEST_STATUSES = {RetentionRequestStatus.OFFERED, RetentionRequestStatus.REJECTED}


def _workflow_recommendation(db: Session, request_id: int) -> tuple[RetentionWorkflowService, dict, dict]:
    workflow = RetentionWorkflowService(db)
    try:
        state = workflow.state(request_id)
    except RetentionWorkflowError as exc:
        raise HTTPException(status_code=503, detail="Retention workflow is temporarily unavailable") from exc
    if state.get("workflow_status") != WorkflowStatus.AWAITING_MANAGER or not state.get("recommendation"):
        raise RetentionDecisionError("A completed recommendation awaiting manager review is required")
    return workflow, state, state["recommendation"]


def _approved_offer(recommendation: dict) -> dict:
    if recommendation.get("policy_conflict"):
        raise RetentionDecisionError("The recommendation has a policy conflict and cannot be approved")
    offer_type = recommendation.get("offer_type")
    if not offer_type:
        raise RetentionDecisionError("The recommendation does not contain a policy-grounded customer offer")
    return {
        "offer_type": offer_type,
        "discount_percentage": recommendation.get("discount_percentage"),
        "description": recommendation["reason"],
        "policy_sources": recommendation.get("policy_sources", []),
        "policy_limit_percentage": recommendation.get("policy_limit_percentage"),
    }


def _modified_offer(recommendation: dict, payload: ManagerDecisionCreate) -> dict:
    assert payload.modified_offer is not None
    modified = payload.modified_offer
    if recommendation.get("policy_conflict"):
        raise RetentionDecisionError("A policy-conflicted recommendation cannot be modified into an offer")

    # Phase 9 does not invent a new policy taxonomy.  A manager may tailor the
    # already retrieved/recommended offer, but may not change it to an unrelated
    # offer category that this deterministic layer cannot validate.
    if modified.offer_type != recommendation.get("offer_type"):
        raise RetentionDecisionError("Modified offer type must match the policy-grounded recommendation")

    policy_limit = recommendation.get("policy_limit_percentage")
    if modified.discount_percentage is not None:
        if policy_limit is None:
            raise RetentionDecisionError("Retrieved policy did not establish a discount limit for this modification")
        if modified.discount_percentage > float(policy_limit):
            raise RetentionDecisionError("Modified discount exceeds the retrieved policy limit")
    elif recommendation.get("discount_percentage") is not None:
        # A rate discount recommendation cannot be converted into an unbounded
        # non-numeric discount; this keeps validation deterministic.
        raise RetentionDecisionError("A modified rate-discount offer requires a discount percentage")

    return {
        "offer_type": modified.offer_type,
        "discount_percentage": modified.discount_percentage,
        "description": modified.description,
        "policy_sources": recommendation.get("policy_sources", []),
        "policy_limit_percentage": policy_limit,
    }


def decide_retention_request(
    db: Session, request_id: int, manager: User, payload: ManagerDecisionCreate
) -> tuple[RetentionDecision, str]:
    """Persist exactly one terminal manager decision and (if accepted) customer offer."""

    request = db.query(RetentionRequest).filter_by(request_id=request_id).with_for_update().first()
    if not request:
        raise HTTPException(status_code=404, detail="Retention request not found")
    if request.status not in {RetentionRequestStatus.PENDING, RetentionRequestStatus.IN_REVIEW} or request.decisions:
        raise RetentionDecisionError("This retention request already has a final manager decision")
    expected = BookingStatus.CONFIRMED if request.request_kind == "proactive" else BookingStatus.CANCEL_PENDING
    if request.booking.status != expected:
        raise RetentionDecisionError("Booking is no longer eligible for this retention decision")

    workflow, _state, original = _workflow_recommendation(db, request_id)
    final_offer: dict | None = None
    action = DecisionAction(payload.action.value)
    workflow_status: str

    if payload.action is ManagerDecisionAction.APPROVE:
        final_offer = _approved_offer(original)
        workflow_status = WorkflowStatus.MANAGER_APPROVED
    elif payload.action is ManagerDecisionAction.MODIFY:
        final_offer = _modified_offer(original, payload)
        workflow_status = WorkflowStatus.MANAGER_MODIFIED
    else:
        workflow_status = WorkflowStatus.MANAGER_REJECTED

    # Keep the source recommendation in business/audit storage as well as the
    # checkpoint. This is the immutable comparison point for a MODIFY decision.
    request.recommended_offer = original
    request.manager_id = manager.user_id
    request.status = RetentionRequestStatus.OFFERED if final_offer else RetentionRequestStatus.REJECTED
    decision_payload = {"original_recommendation": original, "final_customer_offer": final_offer}
    decision = RetentionDecision(
        request_id=request.request_id,
        manager_id=manager.user_id,
        action=action,
        final_offer=decision_payload,
        reason=payload.comment,
    )
    db.add(decision)
    db.flush()

    if final_offer:
        db.add(Offer(
            customer_id=request.customer_id,
            booking_id=request.booking_id,
            offer_type=final_offer["offer_type"],
            discount=(Decimal(str(final_offer["discount_percentage"])) if final_offer["discount_percentage"] is not None else None),
            description=final_offer["description"],
            source="manager_decision",
            status=OfferStatus.AVAILABLE_TO_CUSTOMER,
        ))

    event = {
        ManagerDecisionAction.APPROVE: "retention.manager_approved",
        ManagerDecisionAction.MODIFY: "retention.manager_modified",
        ManagerDecisionAction.REJECT: "retention.manager_rejected",
    }[payload.action]
    log_event(
        db, event, "retention_request", request.request_id,
        {"decision_id": decision.decision_id, "action": payload.action.value, "customer_offer_published": final_offer is not None},
        manager.user_id,
    )
    try:
        workflow.record_manager_decision(request_id, workflow_status, {
            "decision_id": decision.decision_id,
            "action": payload.action.value,
            "manager_id": manager.user_id,
        })
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(decision)
    return decision, workflow_status
