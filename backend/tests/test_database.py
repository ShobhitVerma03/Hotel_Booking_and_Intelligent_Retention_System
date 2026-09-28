import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.base import Base
import backend.app.models  # noqa: F401
from backend.app.models.entities import Customer, Room, User
from backend.app.models.enums import RoomStatus, UserRole
from backend.app.schemas.booking import BookingCreate
from backend.app.services.booking import create_booking


class DatabaseIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        user = User(email="guest@example.com", role=UserRole.CUSTOMER)
        self.customer = Customer(name="Test Guest", email="guest@example.com", phone="5550100", user=user)
        self.room = Room(room_number="T101", room_type="Standard", price_per_night=Decimal("100.00"), capacity=2, status=RoomStatus.AVAILABLE)
        self.db.add_all([self.customer, self.room])
        self.db.commit()
        self.db.refresh(self.customer)
        self.db.refresh(self.room)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_normalized_tables_are_created(self) -> None:
        tables = set(Base.metadata.tables)
        self.assertTrue({"users", "customers", "rooms", "bookings", "offers", "retention_requests", "retention_decisions", "audit_logs"}.issubset(tables))

    def test_booking_calculates_total_and_prevents_overlap(self) -> None:
        payload = BookingCreate(customer_id=self.customer.customer_id, room_id=self.room.room_id, check_in=date(2026, 10, 1), check_out=date(2026, 10, 4), guests=2)
        booking = create_booking(self.db, payload)
        self.assertEqual(booking.total_amount, Decimal("270.00"))
        with self.assertRaises(Exception):
            create_booking(self.db, payload)
