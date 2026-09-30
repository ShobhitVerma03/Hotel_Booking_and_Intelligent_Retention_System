"""Regression tests for persistent customer/manager flows and deployment settings."""
import os
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-with-at-least-thirty-two-characters")
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.main import app
from backend.app.core.config import Settings, get_settings
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.models.entities import Room, User, Booking, Customer, RetentionRequest
from backend.app.models.enums import UserRole
from backend.app.services.auth import hash_password
from backend.app.services.rag import PolicyIngestionService, PolicyRAGService
from backend.app.workflows.retention import RetentionWorkflowService, _recommendation
from backend.ml.features import customer_features


class CompleteFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        def dependency():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = dependency
        self.client = TestClient(app)
        with self.Session() as db:
            db.add_all([User(email="manager@tests.com", password_hash=hash_password("test-manager-password"), role=UserRole.MANAGER), Room(room_number="1", room_type="Standard", capacity=2, price_per_night=100)])
            db.commit()
        self.manager = self.login("manager@tests.com", "test-manager-password")
        r = self.client.post("/api/v1/auth/register", json={"email":"guest@tests.com", "name":"Guest", "password":"test-guest-password"}).json()
        self.customer = {"Authorization": "Bearer " + r["access_token"]}
        self.cid = r["user"]["customer_id"]
        self.old_path = get_settings().langgraph_checkpoint_path
        self.checkpoint_prefix = "backend/data/test-flow-" + uuid.uuid4().hex
        get_settings().langgraph_checkpoint_path = self.checkpoint_prefix + ".db"

    def tearDown(self):
        get_settings().langgraph_checkpoint_path = self.old_path
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, email, password):
        r = self.client.post("/api/v1/auth/login", json={"email":email, "password":password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    def book(self, day):
        r = self.client.post("/api/v1/bookings", headers=self.customer, json={"customer_id":self.cid, "room_id":1, "check_in":f"2028-01-{day:02}", "check_out":f"2028-01-{day+1:02}", "guests":2})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def cancel(self, booking):
        r = self.client.post(f"/api/v1/bookings/{booking['booking_id']}/cancellation-request", headers=self.customer, json={"reason":"Plans changed"})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["request_id"]

    def test_cancellation_approve_reject_authorization_and_refresh(self):
        for day, action, expected in [(1,"approve_cancellation","cancelled"), (3,"decline_cancellation","confirmed")]:
            with patch("backend.app.services.booking.prepare_retention"):
                b = self.book(day)
            rid = self.cancel(b)
            url = f"/api/v1/admin/cancellation-requests/{rid}/resolution"
            self.assertEqual(self.client.post(url, headers=self.customer, json={"action":action}).status_code, 403)
            self.assertEqual(self.client.post(url, headers=self.manager, json={"action":action}).status_code, 200)
            self.assertEqual(self.client.post(url, headers=self.manager, json={"action":action}).status_code, 409)
            fresh = self.client.get(f"/api/v1/bookings/{b['booking_id']}", headers=self.customer).json()
            self.assertEqual(fresh["status"], expected)
            self.assertIn("approved" if expected == "cancelled" else "rejected", fresh["retention_requests"][0]["message"])
        self.assertEqual(self.client.post("/api/v1/customers/identify", json={"email":"guest@tests.com"}).status_code, 401)

    def test_second_booking_real_policy_manager_path_and_checkpoint_loss(self):
        first = self.book(1)
        rid = self.cancel(first)
        self.client.post(f"/api/v1/admin/cancellation-requests/{rid}/resolution", headers=self.manager, json={"action":"approve_cancellation"})
        # Real PDF, embedding model and Chroma retrieval; control risk to test LOW branch.
        PolicyIngestionService().ingest_policy()
        with patch("backend.app.workflows.retention.predict", return_value={"risk_score":0.2,"risk_category":"LOW"}):
            second = self.book(3)
        rid = second["retention_requests"][0]["request_id"]
        with self.Session() as db:
            features = customer_features(db, db.get(Customer, self.cid), db.get(Booking, second["booking_id"]))
            self.assertEqual(features["previous_bookings"], 1)
            self.assertEqual(features["previous_cancellations"], 1)
            self.assertEqual(features["average_previous_booking_value_inr"], 90)
            state = db.get(RetentionRequest, rid).workflow_state
            self.assertEqual(state["recommendation"]["discount_percentage"], 5)
            self.assertEqual(state["recommendation"]["offer_type"], "future_stay_discount_voucher")
            get_settings().langgraph_checkpoint_path = self.checkpoint_prefix + "-empty.db"
            self.assertEqual(RetentionWorkflowService(db).state(rid), state)
        r = self.client.post(f"/api/v1/admin/retention-requests/{rid}/decision", headers=self.manager, json={"action":"approve"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post(f"/api/v1/bookings/retention-requests/{rid}/response", headers=self.customer, json={"action":"accept"})
        self.assertEqual(r.json()["status"], "accepted")
        self.assertEqual(self.client.post(f"/api/v1/bookings/retention-requests/{rid}/response", headers=self.customer, json={"action":"accept"}).status_code, 409)
        fresh = self.client.get(f"/api/v1/bookings/{second['booking_id']}", headers=self.customer).json()
        self.assertEqual(fresh["final_amount"], "100.00")

    def test_real_medium_policy_automatic_branch_and_customer_rejection(self):
        self.book(1)
        PolicyIngestionService().ingest_policy()
        with patch("backend.app.workflows.retention.predict", return_value={"risk_score":0.5,"risk_category":"MEDIUM"}):
            second = self.book(3)
        rid = second["retention_requests"][0]["request_id"]
        with self.Session() as db:
            state = db.get(RetentionRequest, rid).workflow_state
            self.assertEqual(state["workflow_status"], "AUTO_OFFERED")
            self.assertEqual(state["recommendation"]["offer_type"], "complimentary_breakfast")
        response = self.client.post(f"/api/v1/bookings/retention-requests/{rid}/response", headers=self.customer, json={"action":"reject"})
        self.assertEqual(response.json()["status"], "rejected")
        self.assertEqual(response.json()["booking_status"], "confirmed")
        missing = _recommendation({"risk_category":"MEDIUM", "policy_context":"No matching policy", "policy_results":[]})
        self.assertTrue(missing["policy_conflict"])
        self.assertTrue(missing["requires_manager_review"])

    def test_ownership_and_production_configuration(self):
        b = self.book(1)
        other = self.client.post("/api/v1/auth/register", json={"email":"other@tests.com", "name":"Other", "password":"test-other-password"}).json()
        headers = {"Authorization":"Bearer " + other["access_token"]}
        self.assertEqual(self.client.get(f"/api/v1/bookings/{b['booking_id']}", headers=headers).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/bookings/{b['booking_id']}/cancellation-request", headers=headers, json={}).status_code, 404)
        valid = dict(_env_file=None, app_env="production", jwt_secret_key="x"*40, database_url="postgres://user:pass@db/hotel", cors_origins="https://customer.example,https://manager.example")
        self.assertTrue(Settings(**valid).database_url.startswith("postgresql+psycopg://"))
        for key, value in [("jwt_secret_key",""), ("cors_origins","*"), ("database_url","sqlite://"), ("cors_origins","http://localhost:8082")]:
            with self.assertRaises(ValueError):
                Settings(**{**valid,key:value})
