import os
import unittest

# Discovery imports this module first.  Set a test-only secret before the
# application's cached settings are imported; production still has no default.
os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-at-least-thirty-two-characters"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.services.auth import create_access_token, hash_password
from backend.app.models.entities import Customer, User
from backend.app.models.enums import UserRole
import backend.app.models  # noqa: F401


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        with cls.Session() as db:
            manager = User(email="api-manager@example.com", role=UserRole.MANAGER)
            db.add(manager); db.commit()
            cls.manager_headers = {"Authorization": "Bearer " + create_access_token(manager.user_id, "manager")}

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_root_endpoint(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "running")
        self.assertEqual(response.json()["health"], "/api/v1/health")

    def test_create_customer_and_retrieve_it(self) -> None:
        response = self.client.post("/api/v1/customers", headers=self.manager_headers, json={"name": "API Guest", "email": "api.guest@example.com", "phone": "5550101"})
        self.assertEqual(response.status_code, 201)
        customer_id = response.json()["customer_id"]
        db = self.Session(); customer = db.get(Customer, customer_id); customer.user.password_hash = hash_password("test-password-123"); db.commit(); token = create_access_token(customer.user.user_id, customer.user.role.value); db.close()
        self.assertEqual(self.client.get(f"/api/v1/customers/{customer_id}", headers={"Authorization": f"Bearer {token}"}).status_code, 200)

    def test_identify_customer_is_normalized_and_idempotent(self) -> None:
        payload = {"name": "Lifecycle Guest", "email": " Lifecycle@Example.COM ", "phone": "5550102"}
        first = self.client.post("/api/v1/customers/identify", headers=self.manager_headers, json=payload)
        second = self.client.post("/api/v1/customers/identify", headers=self.manager_headers, json={**payload, "email": "lifecycle@example.com"})
        self.assertEqual(first.status_code, 200); self.assertEqual(first.json()["customer_type"], "first_time")
        self.assertEqual(second.json()["customer_type"], "returning")
        self.assertEqual(first.json()["customer"]["customer_id"], second.json()["customer"]["customer_id"])

    def test_booking_lifecycle_and_cancellation_request(self) -> None:
        customer = self.client.post("/api/v1/customers/identify", headers=self.manager_headers, json={"name": "Booking Guest", "email": "booking@example.com", "phone": "5550103"}).json()["customer"]
        from backend.app.models.entities import Room
        db = self.Session(); profile = db.get(Customer, customer["customer_id"]); profile.user.password_hash = hash_password("test-password-123"); room = Room(room_number="L101", room_type="Standard", price_per_night=100, capacity=2); db.add(room); db.commit(); db.refresh(room); token = create_access_token(profile.user.user_id, profile.user.role.value); db.close(); headers={"Authorization": f"Bearer {token}"}
        booking = self.client.post("/api/v1/bookings", json={"customer_id": customer["customer_id"], "room_id": room.room_id, "check_in": "2026-11-01", "check_out": "2026-11-03", "guests": 2}, headers=headers)
        self.assertEqual(booking.status_code, 201); booking_id = booking.json()["booking_id"]
        self.assertEqual(booking.json()["total_amount"], "180.00")
        self.assertEqual(self.client.get("/api/v1/rooms/available?check_in=2026-11-01&check_out=2026-11-03").json(), [])
        cancel = self.client.post(f"/api/v1/bookings/{booking_id}/cancellation-request", json={"reason": "Plans changed"}, headers=headers)
        self.assertEqual(cancel.status_code, 201); self.assertEqual(cancel.json()["status"], "pending")
        retention = self.client.get(f"/api/v1/bookings/retention-requests/{cancel.json()['request_id']}", headers=headers)
        self.assertEqual(retention.status_code, 200); self.assertIsNone(retention.json()["offer"])
        self.assertEqual(self.client.get(f"/api/v1/bookings/{booking_id}", headers=headers).json()["status"], "cancel_pending")
        self.assertEqual(self.client.post(f"/api/v1/bookings/{booking_id}/cancellation-request", json={}, headers=headers).status_code, 409)
