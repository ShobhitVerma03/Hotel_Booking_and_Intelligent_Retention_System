"""Persistent manager resolution of a customer's cancellation request.

This is intentionally separate from Phase 9's retention-offer decision.  A
manager can either finalise the requested cancellation or send the request into
the existing recommendation/HITL path; one action never pretends to be the
other.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.entities import RetentionRequest, User
from backend.app.models.enums import BookingStatus, RetentionRequestStatus
from backend.app.schemas.retention import CancellationResolutionAction, CancellationResolutionCreate
from backend.app.services.audit import log_event


def resolve_cancellation_request(
    db: Session, request_id: int, manager: User, payload: CancellationResolutionCreate
) -> RetentionRequest:
    request = db.get(RetentionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cancellation request not found")
    if request.decisions or request.status in {
        RetentionRequestStatus.OFFERED,
        RetentionRequestStatus.REJECTED,
        RetentionRequestStatus.CANCELLED,
        RetentionRequestStatus.COMPLETED,
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This cancellation request has already been resolved")
    if request.booking.status != BookingStatus.CANCEL_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only cancel-pending bookings can be resolved")

    request.manager_id = manager.user_id
    if payload.action is CancellationResolutionAction.APPROVE_CANCELLATION:
        request.status = RetentionRequestStatus.CANCELLED
        request.booking.status = BookingStatus.CANCELLED
        event = "booking.cancellation_approved"
    else:
        request.status = RetentionRequestStatus.REJECTED
        request.booking.status = BookingStatus.CONFIRMED
        event = "booking.cancellation_declined"

    log_event(
        db,
        event,
        "retention_request",
        request.request_id,
        {"booking_id": request.booking_id, "comment": payload.comment},
        manager.user_id,
    )
    db.commit()
    db.refresh(request)
    return request
