import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-at-least-thirty-two-characters"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.core.config import get_settings
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.entities import AuditLog, Booking, Customer, Offer, RetentionDecision, RetentionRequest, Room, User
from backend.app.models.enums import BookingStatus, RetentionRequestStatus, UserRole
from backend.app.services.auth import create_access_token, hash_password
from backend.app.services.rag import RAGError
from backend.app.workflows.retention import RetentionWorkflowService, WorkflowStatus, _recommendation, get_retention_checkpointer
from backend.ml.features import customer_features


HIGH_RISK_POLICY = [{
    "text": "High-Risk Guests. Standard Permitted Actions include Room rate discount up to 15%.",
    "source": "Company_Retention_Policy_2026.pdf",
    "page": 4,
    "chunk_id": "company-retention-policy-2026-p4-c0",
    "distance": 0.1,
}]

LOW_RISK_POLICY = [{
    "text": "Low-Risk Guests. Future-stay incentive: \u25cf 5% discount voucher. Discounts on current booking are prohibited.",
    "source": "Company_Retention_Policy_2026.pdf",
    "page": 3,
    "chunk_id": "company-retention-policy-2026-p3-c0",
    "distance": 0.1,
}]


class RetentionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.old_checkpoint = cls.settings.langgraph_checkpoint_path
        cls.settings.langgraph_checkpoint_path = "backend/data/langgraph_test_checkpoints.db"
        checkpoint = Path(cls.settings.langgraph_checkpoint_path)
        checkpoint.unlink(missing_ok=True)
        get_retention_checkpointer.cache_clear()

        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

        def override():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override
        cls.client = TestClient(app)
        db = cls.Session()
        cls.manager = User(email="workflow-manager@example.com", password_hash=hash_password("manager-password"), role=UserRole.MANAGER)
        returning_user = User(email="workflow-returning@example.com", password_hash=hash_password("customer-password"), role=UserRole.CUSTOMER)
        cold_user = User(email="workflow-cold@example.com", password_hash=hash_password("customer-password"), role=UserRole.CUSTOMER)
        cls.returning = Customer(name="Returning Guest", email="workflow-returning@example.com", user=returning_user, loyalty_tier="silver")
        cls.cold = Customer(name="Cold Guest", email="workflow-cold@example.com", user=cold_user)
        room = Room(room_number="WF-101", room_type="suite", price_per_night=Decimal("6000"), capacity=2)
        db.add_all([cls.manager, cls.returning, cls.cold, room])
        db.flush()
        for month in (1, 2):
            db.add(Booking(customer_id=cls.returning.customer_id, room_id=room.room_id, check_in=date(2026, month, 1), check_out=date(2026, month, 3), guests=2, total_amount=Decimal("12000"), status=BookingStatus.COMPLETED))
        db.flush()
        returning_current = Booking(customer_id=cls.returning.customer_id, room_id=room.room_id, check_in=date(2026, 5, 1), check_out=date(2026, 5, 3), guests=2, total_amount=Decimal("12000"), status=BookingStatus.CANCEL_PENDING)
        cold_current = Booking(customer_id=cls.cold.customer_id, room_id=room.room_id, check_in=date(2026, 6, 1), check_out=date(2026, 6, 3), guests=2, total_amount=Decimal("12000"), status=BookingStatus.CANCEL_PENDING)
        db.add_all([returning_current, cold_current])
        db.flush()
        cls.returning_request = RetentionRequest(booking_id=returning_current.booking_id, customer_id=cls.returning.customer_id, status=RetentionRequestStatus.PENDING, reason="Plans changed")
        cls.cold_request = RetentionRequest(booking_id=cold_current.booking_id, customer_id=cls.cold.customer_id, status=RetentionRequestStatus.PENDING)
        db.add_all([cls.returning_request, cls.cold_request])
        db.commit()
        cls.manager_id = cls.manager.user_id
        cls.returning_id = cls.returning.customer_id
        cls.cold_id = cls.cold.customer_id
        cls.returning_request_id = cls.returning_request.request_id
        cls.cold_request_id = cls.cold_request.request_id
        cls.returning_booking_id = returning_current.booking_id
        db.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.settings.langgraph_checkpoint_path = cls.old_checkpoint
        get_retention_checkpointer.cache_clear()

    def test_returning_state_graph_policy_limit_checkpoint_and_resumability(self):
        db = self.Session()
        self.assertIsNotNone(customer_features(db, db.get(Customer, self.returning_id)))
        before = (db.get(Booking, self.returning_booking_id).status, db.get(RetentionRequest, self.returning_request_id).status, db.query(Offer).count(), db.query(RetentionDecision).count(), db.query(AuditLog).count())
        with patch("backend.app.workflows.retention.predict", return_value={"risk_score": 0.82, "risk_category": "HIGH"}), patch("backend.app.workflows.retention.PolicyRAGService.retrieve_policy", return_value=HIGH_RISK_POLICY) as retrieve:
            first = RetentionWorkflowService(db, self.manager_id).run(self.returning_request_id)
            second = RetentionWorkflowService(db, self.manager_id).run(self.returning_request_id)
        self.assertEqual(first["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        self.assertEqual(second["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        self.assertEqual(first["recommendation"]["discount_percentage"], 15.0)
        self.assertEqual(first["recommendation"]["policy_limit_percentage"], 15.0)
        self.assertTrue(first["recommendation"]["requires_manager_review"])
        self.assertFalse(first["recommendation"]["policy_conflict"])
        self.assertEqual(retrieve.call_count, 1)
        snapshot = RetentionWorkflowService(db).graph.get_state({"configurable": {"thread_id": f"retention-request-{self.returning_request_id}"}})
        self.assertEqual(snapshot.values["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        after = (db.get(Booking, self.returning_booking_id).status, db.get(RetentionRequest, self.returning_request_id).status, db.query(Offer).count(), db.query(RetentionDecision).count(), db.query(AuditLog).count())
        self.assertEqual(before[:4], after[:4])
        self.assertEqual(after[4], before[4] + 1)
        db.close()

    def test_cold_start_missing_request_rag_failure_and_policy_conflict(self):
        db = self.Session()
        self.assertIsNone(customer_features(db, db.get(Customer, self.cold_id)))
        with patch("backend.app.workflows.retention.PolicyRAGService.retrieve_policy", return_value=HIGH_RISK_POLICY):
            cold = RetentionWorkflowService(db).run(self.cold_request_id)
        self.assertEqual(cold["risk_category"], "UNKNOWN")
        self.assertIsNone(cold["risk_score"])
        self.assertEqual(cold["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        self.assertIsNone(cold["recommendation"]["discount_percentage"])
        self.assertEqual(RetentionWorkflowService(db).run(999999)["workflow_status"], WorkflowStatus.FAILED)
        with patch("backend.app.workflows.retention.PolicyRAGService.retrieve_policy", side_effect=RAGError("unavailable")):
            request = RetentionRequest(booking_id=self.returning_booking_id, customer_id=self.returning_id, status=RetentionRequestStatus.PENDING)
            db.add(request); db.commit()
            self.assertEqual(RetentionWorkflowService(db).run(request.request_id)["workflow_status"], WorkflowStatus.FAILED)
        with patch("backend.app.workflows.retention.predict", side_effect=RuntimeError("model unavailable")):
            request = RetentionRequest(booking_id=self.returning_booking_id, customer_id=self.returning_id, status=RetentionRequestStatus.PENDING)
            db.add(request); db.commit()
            self.assertEqual(RetentionWorkflowService(db).run(request.request_id)["workflow_status"], WorkflowStatus.FAILED)
        conflict = _recommendation({"risk_category": "HIGH", "policy_results": [{**HIGH_RISK_POLICY[0], "text": "High risk action exists but no numeric rate limit is present."}], "policy_context": "High risk action exists but no numeric rate limit is present."})
        self.assertTrue(conflict["policy_conflict"])
        self.assertIsNone(conflict["discount_percentage"])
        db.close()

    def test_low_risk_recommendation_uses_policy_permitted_future_voucher(self):
        recommendation = _recommendation({
            "risk_category": "LOW",
            "policy_results": LOW_RISK_POLICY,
            "policy_context": LOW_RISK_POLICY[0]["text"],
        })
        self.assertEqual(recommendation["offer_type"], "future_stay_discount_voucher")
        self.assertEqual(recommendation["discount_percentage"], 5.0)
        self.assertEqual(recommendation["policy_limit_percentage"], 5.0)
        self.assertFalse(recommendation["policy_conflict"])
        self.assertIn("not a discount on the current booking", recommendation["reason"])

    def test_returning_customer_uses_real_phase6_prediction_node(self):
        db = self.Session()
        request = RetentionRequest(booking_id=self.returning_booking_id, customer_id=self.returning_id, status=RetentionRequestStatus.PENDING)
        db.add(request); db.commit()
        with patch("backend.app.workflows.retention.PolicyRAGService.retrieve_policy", return_value=HIGH_RISK_POLICY):
            state = RetentionWorkflowService(db).run(request.request_id)
        self.assertEqual(state["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        self.assertIsInstance(state["risk_score"], float)
        self.assertGreaterEqual(state["risk_score"], 0.0)
        self.assertLessEqual(state["risk_score"], 1.0)
        self.assertIn(state["risk_category"], {"LOW", "MEDIUM", "HIGH"})
        self.assertIn("booking_context", state)
        self.assertIn("customer_context", state)
        db.close()

    def test_manager_api_authorization_and_structured_response(self):
        manager_token = create_access_token(self.manager_id, "manager")
        db = self.Session()
        api_request = RetentionRequest(booking_id=self.returning_booking_id, customer_id=self.returning_id, status=RetentionRequestStatus.PENDING)
        db.add(api_request); db.commit()
        customer = db.get(Customer, self.returning_id)
        customer_token = create_access_token(customer.user_id, "customer")
        endpoint = f"/api/v1/admin/retention-requests/{api_request.request_id}/recommendation"
        self.assertEqual(self.client.post(endpoint).status_code, 401)
        self.assertEqual(self.client.post(endpoint, headers={"Authorization": f"Bearer {customer_token}"}).status_code, 403)
        with patch("backend.app.workflows.retention.predict", return_value={"risk_score": 0.82, "risk_category": "HIGH"}), patch("backend.app.workflows.retention.PolicyRAGService.retrieve_policy", return_value=HIGH_RISK_POLICY):
            response = self.client.post(endpoint, headers={"Authorization": f"Bearer {manager_token}"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        self.assertIn("recommendation", body)
        self.assertTrue(body["recommendation"]["requires_manager_review"])
        db.close()

    def test_manager_cancellation_resolution_is_persisted_and_role_protected(self):
        db = self.Session()
        booking = Booking(
            customer_id=self.returning_id,
            room_id=db.get(Booking, self.returning_booking_id).room_id,
            check_in=date(2027, 3, 1), check_out=date(2027, 3, 3), guests=2,
            total_amount=Decimal("12000"), status=BookingStatus.CANCEL_PENDING,
        )
        db.add(booking); db.flush()
        request = RetentionRequest(booking_id=booking.booking_id, customer_id=self.returning_id, status=RetentionRequestStatus.PENDING)
        db.add(request); db.commit()
        request_id = request.request_id
        customer_token = create_access_token(db.get(Customer, self.returning_id).user_id, "customer")
        manager_token = create_access_token(self.manager_id, "manager")
        endpoint = f"/api/v1/admin/cancellation-requests/{request_id}/resolution"
        self.assertEqual(self.client.post(endpoint, json={"action": "approve_cancellation"}).status_code, 401)
        self.assertEqual(self.client.post(endpoint, headers={"Authorization": f"Bearer {customer_token}"}, json={"action": "approve_cancellation"}).status_code, 403)
        response = self.client.post(endpoint, headers={"Authorization": f"Bearer {manager_token}"}, json={"action": "approve_cancellation", "comment": "Approved after review"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["booking_status"], "cancelled")
        db.expire_all()
        persisted = db.get(RetentionRequest, request_id)
        self.assertEqual(persisted.status, RetentionRequestStatus.CANCELLED)
        self.assertEqual(persisted.booking.status, BookingStatus.CANCELLED)
        self.assertEqual(persisted.manager_id, self.manager_id)
        self.assertTrue(db.query(AuditLog).filter_by(event_type="booking.cancellation_approved", entity_id=str(request_id)).count())
        db.close()

    def _new_awaiting_manager_request(self):
        """Create a separate request/checkpoint so terminal HITL tests are isolated."""
        db = self.Session()
        sequence = db.query(RetentionRequest).count() + 1
        booking = Booking(
            customer_id=self.returning_id,
            room_id=db.get(Booking, self.returning_booking_id).room_id,
            check_in=date(2027, 1, sequence),
            check_out=date(2027, 1, sequence + 2),
            guests=2,
            total_amount=Decimal("12000"),
            status=BookingStatus.CANCEL_PENDING,
        )
        db.add(booking)
        db.flush()
        request = RetentionRequest(
            booking_id=booking.booking_id,
            customer_id=self.returning_id,
            status=RetentionRequestStatus.PENDING,
        )
        db.add(request)
        db.commit()
        request_id = request.request_id
        with patch("backend.app.workflows.retention.predict", return_value={"risk_score": 0.82, "risk_category": "HIGH"}), patch(
            "backend.app.workflows.retention.PolicyRAGService.retrieve_policy", return_value=HIGH_RISK_POLICY
        ):
            state = RetentionWorkflowService(db, self.manager_id).run(request_id)
        self.assertEqual(state["workflow_status"], WorkflowStatus.AWAITING_MANAGER)
        db.close()
        return request_id

    def test_manager_approve_persists_original_recommendation_and_customer_offer(self):
        request_id = self._new_awaiting_manager_request()
        manager_token = create_access_token(self.manager_id, "manager")
        response = self.client.post(
            f"/api/v1/admin/retention-requests/{request_id}/decision",
            headers={"Authorization": f"Bearer {manager_token}"},
            json={"action": "approve", "comment": "Policy-aligned standard offer approved."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_status"], "offered")
        self.assertEqual(response.json()["workflow_status"], WorkflowStatus.MANAGER_APPROVED)
        self.assertEqual(response.json()["final_offer"]["discount_percentage"], 15.0)
        db = self.Session()
        request = db.get(RetentionRequest, request_id)
        self.assertEqual(request.status, RetentionRequestStatus.OFFERED)
        self.assertEqual(request.manager_id, self.manager_id)
        self.assertEqual(request.booking.status, BookingStatus.CANCEL_PENDING)
        self.assertEqual(len(request.decisions), 1)
        self.assertEqual(request.decisions[0].action.value, "approve")
        self.assertEqual(request.decisions[0].final_offer["original_recommendation"]["discount_percentage"], 15.0)
        offer = db.query(Offer).filter(Offer.booking_id == request.booking_id, Offer.source == "manager_decision").one()
        self.assertEqual(offer.status.value, "available_to_customer")
        self.assertEqual(float(offer.discount), 15.0)
        self.assertTrue(db.query(AuditLog).filter_by(event_type="retention.manager_approved", entity_id=str(request_id)).count())
        self.assertEqual(RetentionWorkflowService(db).state(request_id)["workflow_status"], WorkflowStatus.MANAGER_APPROVED)
        db.close()

    def test_manager_modify_finalizes_once_and_enforces_retrieved_limit(self):
        request_id = self._new_awaiting_manager_request()
        manager_token = create_access_token(self.manager_id, "manager")
        endpoint = f"/api/v1/admin/retention-requests/{request_id}/decision"
        too_large = self.client.post(endpoint, headers={"Authorization": f"Bearer {manager_token}"}, json={
            "action": "modify", "modified_offer": {"offer_type": "room_rate_discount", "discount_percentage": 16, "description": "Too large"},
        })
        self.assertEqual(too_large.status_code, 409)
        approved = self.client.post(endpoint, headers={"Authorization": f"Bearer {manager_token}"}, json={
            "action": "modify", "comment": "Tailored to this guest.",
            "modified_offer": {"offer_type": "room_rate_discount", "discount_percentage": 10, "description": "10% room-rate discount"},
        })
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["workflow_status"], WorkflowStatus.MANAGER_MODIFIED)
        self.assertEqual(approved.json()["final_offer"]["discount_percentage"], 10.0)
        duplicate = self.client.post(endpoint, headers={"Authorization": f"Bearer {manager_token}"}, json={"action": "approve"})
        self.assertEqual(duplicate.status_code, 409)
        db = self.Session()
        request = db.get(RetentionRequest, request_id)
        self.assertEqual(request.booking.status, BookingStatus.CANCEL_PENDING)
        self.assertEqual(request.decisions[0].action.value, "modify")
        self.assertEqual(request.decisions[0].reason, "Tailored to this guest.")
        self.assertEqual(request.decisions[0].final_offer["original_recommendation"]["discount_percentage"], 15.0)
        self.assertEqual(RetentionWorkflowService(db).state(request_id)["workflow_status"], WorkflowStatus.MANAGER_MODIFIED)
        db.close()

    def test_manager_rejection_is_audited_without_customer_offer_and_roles_are_protected(self):
        request_id = self._new_awaiting_manager_request()
        endpoint = f"/api/v1/admin/retention-requests/{request_id}/decision"
        customer = self.Session().get(Customer, self.returning_id)
        customer_token = create_access_token(customer.user_id, "customer")
        self.assertEqual(self.client.post(endpoint, json={"action": "reject"}).status_code, 401)
        self.assertEqual(self.client.post(endpoint, headers={"Authorization": f"Bearer {customer_token}"}, json={"action": "reject"}).status_code, 403)
        manager_token = create_access_token(self.manager_id, "manager")
        response = self.client.post(endpoint, headers={"Authorization": f"Bearer {manager_token}"}, json={"action": "reject", "comment": "No suitable policy-grounded offer."})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["final_offer"])
        self.assertEqual(response.json()["workflow_status"], WorkflowStatus.MANAGER_REJECTED)
        db = self.Session()
        request = db.get(RetentionRequest, request_id)
        self.assertEqual(request.status, RetentionRequestStatus.REJECTED)
        self.assertEqual(request.booking.status, BookingStatus.CANCEL_PENDING)
        self.assertEqual(db.query(Offer).filter(Offer.booking_id == request.booking_id, Offer.source == "manager_decision").count(), 0)
        self.assertTrue(db.query(AuditLog).filter_by(event_type="retention.manager_rejected", entity_id=str(request_id)).count())
        self.assertEqual(RetentionWorkflowService(db).state(request_id)["workflow_status"], WorkflowStatus.MANAGER_REJECTED)
        db.close()
