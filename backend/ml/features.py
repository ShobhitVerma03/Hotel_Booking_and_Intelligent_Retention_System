"""Features at booking time: exclude the target booking's eventual outcome."""
from backend.app.models.entities import Booking, Customer, Offer
from backend.app.models.enums import BookingStatus, OfferStatus
from sqlalchemy.orm import Session


def customer_features(db: Session, customer: Customer, booking: Booking | None = None):
    ordered = db.query(Booking).filter_by(customer_id=customer.customer_id).order_by(Booking.booking_id).all()
    current = booking or (ordered[-1] if ordered else None)
    if current is None:
        return None
    previous = [b for b in ordered if b.booking_id < current.booking_id]
    if not previous:
        return None
    cancelled = sum(b.status == BookingStatus.CANCELLED for b in previous)
    offers = db.query(Offer).filter(Offer.customer_id == customer.customer_id,
        Offer.booking_id < current.booking_id, Offer.offer_type != 'first_time_welcome').all()
    created = current.created_at.date()
    return {
        # Missing schema attributes use the fitted encoder's unknown category.
        'city': 'unknown', 'hotel_type': 'unknown',
        'room_type': current.room.room_type.lower(), 'booking_channel': 'direct',
        'previous_bookings': len(previous), 'previous_cancellations': cancelled,
        'completed_stays': sum(b.status == BookingStatus.COMPLETED for b in previous),
        'cancellation_rate': cancelled / len(previous),
        'average_previous_booking_value_inr': sum(float(b.total_amount) for b in previous) / len(previous),
        'current_booking_value_inr': float(current.total_amount),
        'lead_time_days': max(0, (current.check_in - created).days),
        'length_of_stay': (current.check_out - current.check_in).days,
        'number_of_guests': current.guests, 'booking_month': current.check_in.month,
        'customer_tenure_days': max(0, (created - customer.created_at.date()).days),
        'previous_retention_offers': len(offers),
        'previous_offer_acceptance_rate': sum(o.status == OfferStatus.ACCEPTED for o in offers) / len(offers) if offers else 0.0,
        'payment_type': 'unknown', 'weekend_booking': current.check_in.weekday() >= 5,
    }
