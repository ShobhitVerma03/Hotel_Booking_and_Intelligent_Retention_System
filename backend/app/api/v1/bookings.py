from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database.session import get_db
from backend.app.models.entities import Booking, Offer, RetentionRequest
from backend.app.models.enums import OfferStatus, BookingStatus, RetentionRequestStatus
from pydantic import BaseModel
from typing import Literal
from decimal import Decimal
from backend.app.services.audit import log_event
from backend.app.schemas.booking import BookingCreate, BookingResponse, CancellationRequestCreate, CancellationRequestResponse, CustomerRetentionResponse
from backend.app.services.booking import create_booking, request_cancellation
from backend.app.api.dependencies import require_customer
from backend.app.models.entities import User

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking_endpoint(payload: BookingCreate, db: Session = Depends(get_db), user: User = Depends(require_customer)) -> Booking:
    if user.customer.customer_id != payload.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot create a booking for another customer")
    booking = create_booking(db, payload)
    return customer_booking_view(db, booking)


@router.get("/retention-requests/{request_id}", response_model=CustomerRetentionResponse)
def customer_retention_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    """Customer-safe view of a manager-finalized offer; no decision action occurs here."""

    request = db.get(RetentionRequest, request_id)
    if request is None or request.customer_id != user.customer.customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention request not found")
    offer = db.query(Offer).filter(
        Offer.booking_id == request.booking_id,
        Offer.customer_id == request.customer_id,
        Offer.source.in_(["manager_decision", "policy_automatic"]),
        Offer.status == OfferStatus.AVAILABLE_TO_CUSTOMER,
    ).order_by(Offer.created_at.desc()).first()
    if request.status != RetentionRequestStatus.OFFERED:
        offer = None
    return {
        "request_id": request.request_id,
        "booking_id": request.booking_id,
        "customer_id": request.customer_id,
        "status": request.status.value,
        "reason": request.reason,
        "request_kind": request.request_kind,
        "message": retention_message(request),
        "booking_status": request.booking.status,
        "offer": {"offer_id": offer.offer_id, "offer_type": offer.offer_type, "discount": offer.discount, "description": offer.description, "status": offer.status.value} if offer else None,
        "created_at": request.created_at,
    }


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.customer_id != user.customer.customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return customer_booking_view(db, booking)


@router.post("/{booking_id}/cancellation-request", response_model=CancellationRequestResponse, status_code=status.HTTP_201_CREATED)
def cancellation_request(booking_id: int, payload: CancellationRequestCreate, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.customer_id != user.customer.customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return request_cancellation(db, booking, payload.reason)




def customer_booking_view(db: Session, booking: Booking) -> dict:
    offer = db.query(Offer).filter(Offer.booking_id == booking.booking_id, Offer.offer_type == "first_time_welcome").first()
    base_amount = booking.room.price_per_night * (booking.check_out - booking.check_in).days
    fields = {name: getattr(booking, name) for name in ("booking_id", "customer_id", "room_id", "check_in", "check_out", "guests", "total_amount", "status", "created_at")}
    return {**fields, "room_number": booking.room.room_number, "room_type": booking.room.room_type, "base_amount": base_amount, "final_amount": booking.total_amount, "welcome_offer": {"offer_type": offer.offer_type, "discount": offer.discount, "status": offer.status.value} if offer else None, "retention_requests": [{"request_id": r.request_id, "request_kind": r.request_kind, "status": r.status.value, "message": retention_message(r)} for r in sorted(booking.retention_requests, key=lambda r: r.request_id, reverse=True)]}


def retention_message(request):
    if request.status == RetentionRequestStatus.CANCELLED:
        return "Cancellation approved. Your booking is cancelled."
    if request.status == RetentionRequestStatus.REJECTED:
        return "Cancellation rejected. Your booking remains confirmed." if request.request_kind == "cancellation" and request.booking.status == BookingStatus.CONFIRMED else "No retention offer was approved. Cancellation still awaits manager resolution." if request.booking.status == BookingStatus.CANCEL_PENDING else "No retention offer was approved. Your booking remains confirmed."
    if request.status == RetentionRequestStatus.OFFERED:
        return "A hotel offer is available for your review."
    if request.status == RetentionRequestStatus.ACCEPTED:
        return "Offer accepted. Your booking is confirmed."
    if request.status == RetentionRequestStatus.COMPLETED:
        return "This retention review is closed."
    if (request.workflow_state or {}).get("workflow_status") == "FAILED":
        return "Offer preparation is temporarily unavailable. Your request is saved for manager review."
    return "Cancellation is pending manager review." if request.request_kind == "cancellation" else "Your booking is confirmed. A hotel offer is being reviewed."


class OfferResponseCreate(BaseModel):
    action: Literal["accept", "reject"]


@router.post("/retention-requests/{request_id}/response", response_model=CustomerRetentionResponse)
def respond_to_offer(request_id: int, payload: OfferResponseCreate, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    retention = db.query(RetentionRequest).filter_by(request_id=request_id, customer_id=user.customer.customer_id).with_for_update().first()
    if not retention:
        raise HTTPException(404, "Retention request not found")
    if retention.status != RetentionRequestStatus.OFFERED:
        raise HTTPException(409, "No offer is awaiting your response")
    offer = db.query(Offer).filter(Offer.booking_id == retention.booking_id, Offer.source.in_(["manager_decision", "policy_automatic"]), Offer.status == OfferStatus.AVAILABLE_TO_CUSTOMER).with_for_update().first()
    if not offer:
        raise HTTPException(409, "Offer is no longer available")
    accepted = payload.action == "accept"
    offer.status = OfferStatus.ACCEPTED if accepted else OfferStatus.REJECTED
    retention.status = RetentionRequestStatus.ACCEPTED if accepted else RetentionRequestStatus.REJECTED
    if accepted:
        retention.booking.status = BookingStatus.CONFIRMED
        if offer.offer_type == "room_rate_discount" and offer.discount is not None:
            retention.booking.total_amount = (retention.booking.total_amount * (Decimal(100) - offer.discount) / Decimal(100)).quantize(Decimal("0.01"))
    log_event(db, "retention.customer_" + payload.action, "retention_request", request_id, {"offer_id": offer.offer_id}, user.user_id)
    db.commit()
    return customer_retention_request(request_id, db, user)
