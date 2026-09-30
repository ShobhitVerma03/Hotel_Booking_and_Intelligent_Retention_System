from decimal import Decimal

from sqlalchemy.orm import Session

from backend.app.models.entities import Room, User
from backend.app.models.enums import RoomStatus, UserRole
from backend.app.core.config import get_settings
from backend.app.services.auth import hash_password


def seed_database(db: Session) -> None:
    """Insert only non-sensitive local development reference data."""
    if db.query(Room).first() is None:
        db.add_all([
            Room(room_number="101", room_type="Standard", price_per_night=Decimal("120.00"), capacity=2, status=RoomStatus.AVAILABLE),
            Room(room_number="201", room_type="Deluxe", price_per_night=Decimal("185.00"), capacity=2, status=RoomStatus.AVAILABLE),
            Room(room_number="301", room_type="Suite", price_per_night=Decimal("320.00"), capacity=4, status=RoomStatus.AVAILABLE),
        ])
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"} and not settings.dev_manager_password:
        raise ValueError("DEV_MANAGER_PASSWORD is required when SEED_DATABASE=true in production")
    manager = db.query(User).filter(User.email == settings.dev_manager_email).first()
    manager_created = manager is None
    if manager_created:
        manager = User(email=settings.dev_manager_email, role=UserRole.MANAGER)
        db.add(manager)
    # A startup must not silently rotate the manager password. Set the reset
    # flag only for an intentional, controlled local recovery operation.
    if settings.dev_manager_password and (manager_created or settings.reset_seed_manager_password):
        manager.password_hash = hash_password(settings.dev_manager_password)
    db.commit()
