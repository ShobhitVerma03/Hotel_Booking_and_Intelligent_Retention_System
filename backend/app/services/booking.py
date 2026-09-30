from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import Booking, Customer, Offer, RetentionRequest, Room
from backend.app.models.enums import BookingStatus, OfferStatus, RetentionRequestStatus, RoomStatus
from backend.app.schemas.booking import BookingCreate
from backend.app.services.audit import log_event

ACTIVE_REQUESTS = (RetentionRequestStatus.PENDING, RetentionRequestStatus.IN_REVIEW, RetentionRequestStatus.OFFERED)


def room_is_available(db: Session, room: Room, check_in, check_out) -> bool:
    return db.query(Booking).filter(Booking.room_id == room.room_id, Booking.status != BookingStatus.CANCELLED, Booking.check_in < check_out, Booking.check_out > check_in).first() is None


def available_rooms(db: Session, check_in, check_out, capacity=None, room_type=None):
    query = db.query(Room).filter(Room.status == RoomStatus.AVAILABLE)
    if capacity: query = query.filter(Room.capacity >= capacity)
    if room_type: query = query.filter(Room.room_type == room_type)
    return [room for room in query.all() if room_is_available(db, room, check_in, check_out)]


def create_booking(db: Session, payload: BookingCreate) -> Booking:
    customer = db.get(Customer, payload.customer_id)
    room = db.query(Room).filter_by(room_id=payload.room_id).with_for_update().first()
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    if room.status != RoomStatus.AVAILABLE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room is not available")
    if payload.guests > room.capacity:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Guest count exceeds room capacity")

    if not room_is_available(db, room, payload.check_in, payload.check_out):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room is unavailable for these dates")

    nights = (payload.check_out - payload.check_in).days
    first_booking = db.query(Booking).filter(Booking.customer_id == customer.customer_id).count() == 0
    base_amount = Decimal(room.price_per_night) * nights
    discount = Decimal(str(get_settings().first_time_welcome_discount)) if first_booking else Decimal("0")
    booking = Booking(
        **payload.model_dump(),
        total_amount=(base_amount * (Decimal("100") - discount) / Decimal("100")).quantize(Decimal("0.01")),
        status=BookingStatus.CONFIRMED,
    )
    db.add(booking)
    db.flush()
    log_event(db, "booking.created", "booking", booking.booking_id, {"customer_id": customer.customer_id})
    if first_booking:
        db.add(Offer(customer_id=customer.customer_id, booking_id=booking.booking_id, offer_type="first_time_welcome", discount=discount, description=f"First-time customer welcome discount of {discount}%", source="business_rule", status=OfferStatus.ACCEPTED))
        log_event(db, "offer.welcome_created", "booking", booking.booking_id, {"discount": str(discount)})
    else:
        retention = RetentionRequest(booking_id=booking.booking_id, customer_id=customer.customer_id,
            request_kind="proactive", status=RetentionRequestStatus.PENDING)
        db.add(retention)
        db.flush()
    db.commit()
    db.refresh(booking)
    if not first_booking:
        prepare_retention(db, retention.request_id)
    return booking


def request_cancellation(db: Session, booking: Booking, reason: str | None) -> RetentionRequest:
    booking = db.query(Booking).filter_by(booking_id=booking.booking_id).with_for_update().populate_existing().one()
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only confirmed bookings can request cancellation")
    if db.query(RetentionRequest).filter(RetentionRequest.booking_id == booking.booking_id, RetentionRequest.request_kind == "cancellation", RetentionRequest.status.in_(ACTIVE_REQUESTS)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active cancellation request already exists for this booking")
    # Supersede proactive processing for this booking before opening cancellation.
    for previous in db.query(RetentionRequest).filter(RetentionRequest.booking_id == booking.booking_id, RetentionRequest.request_kind == "proactive", RetentionRequest.status.in_(ACTIVE_REQUESTS)):
        previous.status = RetentionRequestStatus.COMPLETED
    for offer in db.query(Offer).filter_by(booking_id=booking.booking_id, status=OfferStatus.AVAILABLE_TO_CUSTOMER):
        offer.status = OfferStatus.EXPIRED
    booking.status = BookingStatus.CANCEL_PENDING
    request = RetentionRequest(booking_id=booking.booking_id, customer_id=booking.customer_id, reason=reason, status=RetentionRequestStatus.PENDING)
    db.add(request); db.flush(); log_event(db, "booking.cancellation_requested", "retention_request", request.request_id, {"booking_id": booking.booking_id}); db.commit(); db.refresh(request)
    return request


def prepare_retention(db: Session, request_id: int) -> None:
    import logging
    from backend.app.workflows.retention import RetentionWorkflowService
    try:
        RetentionWorkflowService(db).run(request_id)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("retention.preparation_failed request_id=%s; manager can retry", request_id)
