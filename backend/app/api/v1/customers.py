from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database.session import get_db
from backend.app.models.entities import Customer, User
from backend.app.models.enums import UserRole
from backend.app.schemas.customer import CustomerCreate, CustomerIdentificationResponse, CustomerIdentify, CustomerResponse
from backend.app.services.customer import identify_customer, normalize_email
from backend.app.api.dependencies import require_customer, require_manager
from backend.app.models.entities import Booking
from backend.app.schemas.booking import CustomerBookingHistoryResponse

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_manager)])
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> Customer:
    email = normalize_email(str(payload.email))
    if db.query(Customer).filter(Customer.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer email already exists")
    user = User(email=email, role=UserRole.CUSTOMER)
    customer = Customer(name=payload.name, email=email, phone=payload.phone, user=user)
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer email or phone already exists")
    db.refresh(customer)
    return customer


@router.post("/identify", response_model=CustomerIdentificationResponse, dependencies=[Depends(require_manager)])
def identify_customer_endpoint(payload: CustomerIdentify, db: Session = Depends(get_db)) -> CustomerIdentificationResponse:
    customer, customer_type = identify_customer(db, payload)
    return CustomerIdentificationResponse(customer=customer, customer_type=customer_type)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)) -> Customer:
    if user.customer.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access another customer's profile")
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.get("/{customer_id}/bookings", response_model=list[CustomerBookingHistoryResponse])
def customer_booking_history(customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_customer)):
    if user.customer.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access another customer's booking history")
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    rows = db.query(Booking).filter(Booking.customer_id == customer_id).order_by(Booking.created_at.desc()).all()
    return [CustomerBookingHistoryResponse(booking_id=row.booking_id, room_number=row.room.room_number, room_type=row.room.room_type, check_in=row.check_in, check_out=row.check_out, status=row.status, booking_amount=row.total_amount, created_at=row.created_at) for row in rows]
