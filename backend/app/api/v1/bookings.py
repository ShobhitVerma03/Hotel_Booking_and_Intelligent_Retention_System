from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database.session import get_db
from backend.app.models.entities import Booking, Offer, RetentionRequest
from backend.app.models.enums import OfferStatus
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
        Offer.source == "manager_decision",
        Offer.status == OfferStatus.AVAILABLE_TO_CUSTOMER,
    ).order_by(Offer.created_at.desc()).first()
    return {
        "request_id": request.request_id,
        "booking_id": request.booking_id,
        "customer_id": request.customer_id,
        "status": request.status.value,
        "reason": request.reason,
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
    return {**BookingResponse.model_validate(booking).model_dump(), "room_number": booking.room.room_number, "room_type": booking.room.room_type, "base_amount": base_amount, "final_amount": booking.total_amount, "welcome_offer": {"offer_type": offer.offer_type, "discount": offer.discount, "status": offer.status.value} if offer else None}
