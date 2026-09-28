from datetime import date
from sqlalchemy.orm import Session
from backend.app.models.entities import Customer, Booking
from backend.app.models.enums import BookingStatus

def customer_features(db:Session, customer:Customer):
    history=[b for b in customer.bookings if b.status in (BookingStatus.CANCELLED,BookingStatus.COMPLETED,BookingStatus.CONFIRMED)]
    if len(history)<2: return None
    cancelled=sum(b.status==BookingStatus.CANCELLED for b in history); completed=sum(b.status==BookingStatus.COMPLETED for b in history); current=history[-1]; values=[float(b.total_amount) for b in history]
    return {'city':'Delhi','hotel_type':'leisure','room_type':current.room.room_type.lower(),'booking_channel':'direct','previous_bookings':len(history)-1,'previous_cancellations':cancelled,'completed_stays':completed,'cancellation_rate':cancelled/len(history),'average_previous_booking_value_inr':sum(values)/len(values),'current_booking_value_inr':float(current.total_amount),'lead_time_days':30,'length_of_stay':(current.check_out-current.check_in).days,'number_of_guests':current.guests,'booking_month':current.check_in.month,'customer_tenure_days':365,'previous_retention_offers':0,'previous_offer_acceptance_rate':0.0,'payment_type':'card','weekend_booking':current.check_in.weekday()>=5}
