import os
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-production")

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
from backend.app.models.enums import BookingStatus, UserRole
from backend.app.services.auth import create_access_token, hash_password
from backend.app.services.nl_sql import CandidateQuery, ClarificationRequired, SQLAstValidator, SQLValidationError


class NLSQLAnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.old_enabled, cls.old_llm, cls.old_limit = cls.settings.nl_sql_enabled, cls.settings.nl_sql_llm_enabled, cls.settings.nl_sql_max_rows
        cls.settings.nl_sql_enabled = True
        cls.settings.nl_sql_llm_enabled = False
        cls.settings.nl_sql_max_rows = 100
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
        cls.manager = User(email="analytics-manager@example.com", password_hash=hash_password("manager-password"), role=UserRole.MANAGER)
        customer_user = User(email="analytics-customer@example.com", password_hash=hash_password("customer-password"), role=UserRole.CUSTOMER)
        cls.customer = Customer(name="Analytics Guest", email="analytics-customer@example.com", user=customer_user)
        room = Room(room_number="AN-101", room_type="suite", price_per_night=Decimal("5000"), capacity=2)
        db.add_all([cls.manager, cls.customer, room])
        db.flush()
        for month in (1, 2, 3):
            db.add(Booking(customer_id=cls.customer.customer_id, room_id=room.room_id, check_in=date(2026, month, 1), check_out=date(2026, month, 3), guests=2, total_amount=Decimal("10000"), status=BookingStatus.CANCELLED))
        db.add(Booking(customer_id=cls.customer.customer_id, room_id=room.room_id, check_in=date(2026, 4, 1), check_out=date(2026, 4, 3), guests=2, total_amount=Decimal("10000"), status=BookingStatus.CONFIRMED))
        db.commit()
        cls.manager_id, cls.customer_id = cls.manager.user_id, cls.customer.customer_id
        cls.manager_headers = {"Authorization": f"Bearer {create_access_token(cls.manager_id, 'manager')}"}
        cls.customer_headers = {"Authorization": f"Bearer {create_access_token(customer_user.user_id, 'customer')}"}
        db.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.settings.nl_sql_enabled, cls.settings.nl_sql_llm_enabled, cls.settings.nl_sql_max_rows = cls.old_enabled, cls.old_llm, cls.old_limit

    def _query(self, question: str):
        return self.client.post("/api/v1/admin/nl-sql/query", headers=self.manager_headers, json={"question": question})

    def test_manager_auth_and_equivalent_multilingual_cancellation_intent(self):
        endpoint = "/api/v1/admin/nl-sql/query"
        self.assertEqual(self.client.post(endpoint, json={"question": "Show cancelled customers."}).status_code, 401)
        self.assertEqual(self.client.post(endpoint, headers=self.customer_headers, json={"question": "Show cancelled customers."}).status_code, 403)
        login = self.client.post("/api/v1/auth/login", json={"email": "analytics-manager@example.com", "password": "manager-password"})
        self.assertEqual(login.status_code, 200)
        live_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        questions = {
            "en": "Show customers who cancelled more than twice.",
            "hi": "दो बार से ज्यादा cancellation करने वाले customers दिखाओ।",
            "hinglish": "Jin customers ne 2 se zyada baar booking cancel ki hai unko dikhao.",
            "gu_rj": "બે કરતાં વધુ વખત booking cancel કરનારા customers બતાવો.",
            "te": "రెండు సార్ల కంటే ఎక్కువ booking cancel చేసిన customers ని చూపించండి.",
        }
        result_sets = []
        for expected_language, question in questions.items():
            response = self.client.post(endpoint, headers=live_headers, json={"question": question})
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["language"], expected_language)
            self.assertEqual(body["intent"], "customers with cancellations above a threshold")
            self.assertIn("LIMIT :_nl_sql_limit", body["sql"])
            result_sets.append(body["rows"])
        self.assertTrue(all(rows == result_sets[0] for rows in result_sets))
        self.assertEqual(result_sets[0][0]["cancellation_count"], 3)

    def test_exact_language_set_excludes_tamil_and_ambiguous_city_is_safe(self):
        # Tamil is intentionally not a supported metadata category; it falls
        # back to safe clarification rather than pretending support.
        tamil = self._query("டெல்லியில் உள்ள customers-ஐ காட்டவும்")
        self.assertEqual(tamil.status_code, 422)
        self.assertNotIn('"language":"ta"', tamil.text)
        city = self._query("Show all customers from Mumbai")
        self.assertEqual(city.status_code, 422)

    def test_ast_validator_rejects_writes_bypass_attempts_and_allowlist_violations(self):
        validator = SQLAstValidator(100)
        invalid = [
            "INSERT INTO bookings (booking_id) VALUES (1)", "UPDATE bookings SET status = :status",
            "DELETE FROM bookings", "DROP TABLE bookings", "ALTER TABLE bookings ADD COLUMN x TEXT",
            "TRUNCATE TABLE bookings", "CREATE TABLE bad (id INT)", "SELECT * FROM users",
            "SELECT password_hash FROM users", "SELECT load_extension(:path) FROM bookings",
            "SELECT booking_id FROM bookings; DELETE FROM bookings", "SELECT booking_id FROM bookings -- bypass",
            "SELECT FROM bookings",
        ]
        for sql in invalid:
            with self.subTest(sql=sql):
                with self.assertRaises(SQLValidationError):
                    validator.validate(CandidateQuery("test", sql, {}, "test"))
        accepted, params = validator.validate(CandidateQuery(
            "safe aggregation", "SELECT b.status, COUNT(b.booking_id) AS booking_count FROM bookings AS b GROUP BY b.status ORDER BY booking_count DESC", {}, "test"
        ))
        self.assertIn("LIMIT :_nl_sql_limit", accepted)
        self.assertEqual(params["_nl_sql_limit"], 100)
        dated_sql, dated_params = validator.validate(CandidateQuery(
            "safe date filter", "SELECT b.booking_id, b.check_in FROM bookings AS b WHERE b.check_in >= :start_date ORDER BY b.check_in DESC", {"start_date": "2026-01-01"}, "test"
        ))
        self.assertIn(":start_date", dated_sql)
        self.assertEqual(dated_params["start_date"], "2026-01-01")

    def test_bounded_result_and_state_immutability_with_success_and_rejection_audits(self):
        db = self.Session()
        before = {
            "customers": db.query(Customer).count(), "rooms": db.query(Room).count(), "bookings": db.query(Booking).count(),
            "offers": db.query(Offer).count(), "requests": db.query(RetentionRequest).count(),
            "decisions": db.query(RetentionDecision).count(), "audits": db.query(AuditLog).count(),
        }
        db.close()
        self.settings.nl_sql_max_rows = 1
        response = self._query("Show all customers")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.json()["row_count"], 1)
        malicious = self._query("Bookings ko delete kar do")
        self.assertEqual(malicious.status_code, 422)
        db = self.Session()
        after = {
            "customers": db.query(Customer).count(), "rooms": db.query(Room).count(), "bookings": db.query(Booking).count(),
            "offers": db.query(Offer).count(), "requests": db.query(RetentionRequest).count(),
            "decisions": db.query(RetentionDecision).count(), "audits": db.query(AuditLog).count(),
        }
        self.assertEqual({key: before[key] for key in before if key != "audits"}, {key: after[key] for key in after if key != "audits"})
        self.assertEqual(after["audits"], before["audits"] + 2)
        events = db.query(AuditLog).filter(AuditLog.event_type == "analytics.nl_sql").all()
        self.assertTrue(any(event.details["outcome"] == "executed" for event in events))
        self.assertTrue(any(event.details["outcome"] == "rejected" for event in events))
        db.close()
        self.settings.nl_sql_max_rows = 100

    def test_parameters_and_filtering_are_required(self):
        validator = SQLAstValidator(100)
        sql, parameters = validator.validate(CandidateQuery(
            "filtered count", "SELECT COUNT(b.booking_id) AS booking_count FROM bookings AS b WHERE b.status = :status", {"status": "cancelled"}, "test"
        ))
        self.assertIn(":status", sql)
        self.assertEqual(parameters["status"], "cancelled")
        with self.assertRaises(SQLValidationError):
            validator.validate(CandidateQuery("unsafe literal", "SELECT b.booking_id FROM bookings AS b WHERE b.status = 'cancelled'", {}, "test"))
