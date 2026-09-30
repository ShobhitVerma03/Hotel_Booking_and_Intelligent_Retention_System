from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base
from backend.app.models.enums import (
    BookingStatus, DecisionAction, OfferStatus, RetentionRequestStatus, RoomStatus, UserRole,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.CUSTOMER)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="user", uselist=False)
    decisions: Mapped[list["RetentionDecision"]] = relationship(back_populates="manager")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    loyalty_tier: Mapped[str] = mapped_column(String(30), default="bronze", nullable=False)
    user: Mapped[Optional[User]] = relationship(back_populates="customer")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="customer")
    offers: Mapped[list["Offer"]] = relationship(back_populates="customer")
    retention_requests: Mapped[list["RetentionRequest"]] = relationship(back_populates="customer")


class Room(TimestampMixin, Base):
    __tablename__ = "rooms"

    room_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    room_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    price_per_night: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RoomStatus] = mapped_column(Enum(RoomStatus), default=RoomStatus.AVAILABLE, nullable=False)
    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"

    booking_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.CONFIRMED, nullable=False)
    customer: Mapped[Customer] = relationship(back_populates="bookings")
    room: Mapped[Room] = relationship(back_populates="bookings")
    offers: Mapped[list["Offer"]] = relationship(back_populates="booking")
    retention_requests: Mapped[list["RetentionRequest"]] = relationship(back_populates="booking")


class Offer(TimestampMixin, Base):
    __tablename__ = "offers"

    offer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False)
    booking_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookings.booking_id", ondelete="SET NULL"))
    offer_type: Mapped[str] = mapped_column(String(100), nullable=False)
    discount: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus), default=OfferStatus.DRAFT, nullable=False)
    customer: Mapped[Customer] = relationship(back_populates="offers")
    booking: Mapped[Optional[Booking]] = relationship(back_populates="offers")


class RetentionRequest(TimestampMixin, Base):
    __tablename__ = "retention_requests"

    request_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.booking_id", ondelete="RESTRICT"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False)
    risk_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    risk_level: Mapped[Optional[str]] = mapped_column(String(20))
    recommended_offer: Mapped[Optional[dict]] = mapped_column(JSON)
    policy_reference: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[RetentionRequestStatus] = mapped_column(
        Enum(RetentionRequestStatus), default=RetentionRequestStatus.PENDING, nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text)
    request_kind: Mapped[str] = mapped_column(String(20), default="cancellation", server_default="cancellation", nullable=False)
    workflow_state: Mapped[Optional[dict]] = mapped_column(JSON)
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    booking: Mapped[Booking] = relationship(back_populates="retention_requests")
    customer: Mapped[Customer] = relationship(back_populates="retention_requests")
    decisions: Mapped[list["RetentionDecision"]] = relationship(back_populates="retention_request")


class RetentionDecision(TimestampMixin, Base):
    __tablename__ = "retention_decisions"

    decision_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("retention_requests.request_id", ondelete="CASCADE"), nullable=False)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[DecisionAction] = mapped_column(Enum(DecisionAction), nullable=False)
    final_offer: Mapped[Optional[dict]] = mapped_column(JSON)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    retention_request: Mapped[RetentionRequest] = relationship(back_populates="decisions")
    manager: Mapped[User] = relationship(back_populates="decisions")


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    audit_log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    actor: Mapped[Optional[User]] = relationship(back_populates="audit_logs")
