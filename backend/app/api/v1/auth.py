from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend.app.api.dependencies import get_current_user
from backend.app.database.session import get_db
from backend.app.models.entities import Customer, User
from backend.app.models.enums import UserRole
from backend.app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from backend.app.services.audit import log_event
from backend.app.services.auth import create_access_token, hash_password, verify_password
from backend.app.services.customer import normalize_email

router = APIRouter(prefix="/auth", tags=["auth"])

def user_view(user: User) -> UserResponse:
    return UserResponse(user_id=user.user_id, email=user.email, role=user.role.value, is_active=user.is_active, customer_id=user.customer.customer_id if user.customer else None)

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email))
    if db.query(User).filter(User.email == email).first(): raise HTTPException(409, "An account already exists for this email")
    customer = db.query(Customer).filter(Customer.email == email).first()
    if customer:
        raise HTTPException(409, "An existing guest profile requires staff-assisted account setup")
    user = User(email=email, password_hash=hash_password(payload.password), role=UserRole.CUSTOMER)
    if customer: customer.user = user
    else: customer = Customer(name=payload.name, email=email, phone=payload.phone.strip() or None if payload.phone else None, user=user); db.add(customer)
    try:
        db.add(user); db.flush(); log_event(db, "auth.registered", "user", user.user_id, {"role": "customer"}, user.user_id); db.commit(); db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email or phone already exists")
    return TokenResponse(access_token=create_access_token(user.user_id, user.role.value), user=user_view(user))

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = normalize_email(str(payload.email)); user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        if user: log_event(db, "auth.login_failed", "user", user.user_id); db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    log_event(db, "auth.login", "user", user.user_id, {"role": user.role.value}, user.user_id); db.commit()
    return TokenResponse(access_token=create_access_token(user.user_id, user.role.value), user=user_view(user))

@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return user_view(user)
