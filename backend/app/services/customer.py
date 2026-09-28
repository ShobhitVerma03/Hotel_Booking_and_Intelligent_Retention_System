from sqlalchemy.orm import Session
from backend.app.models.entities import Customer, User
from backend.app.models.enums import UserRole
from backend.app.schemas.customer import CustomerIdentify
from backend.app.services.audit import log_event


def normalize_email(email: str) -> str:
    return email.strip().lower()


def identify_customer(db: Session, payload: CustomerIdentify) -> tuple[Customer, str]:
    email = normalize_email(str(payload.email))
    customer = db.query(Customer).filter(Customer.email == email).first()
    if customer:
        return customer, "returning"
    customer = Customer(name=payload.name.strip(), email=email, phone=payload.phone, user=User(email=email, role=UserRole.CUSTOMER))
    db.add(customer); db.flush(); log_event(db, "customer.created", "customer", customer.customer_id, {"email": email}); db.commit(); db.refresh(customer)
    return customer, "first_time"
