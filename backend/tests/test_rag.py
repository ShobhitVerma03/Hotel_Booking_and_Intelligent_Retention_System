import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-with-at-least-thirty-two-characters")

import chromadb
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.api.dependencies import require_manager
from backend.app.core.config import get_settings
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.entities import AuditLog, Booking, Customer, Offer, RetentionDecision, RetentionRequest, Room, User
from backend.app.models.enums import BookingStatus, RetentionRequestStatus, UserRole
from backend.app.services.auth import create_access_token, hash_password
from backend.app.services.rag import PolicyIngestionService, PolicyRAGService, RAGError, RAGValidationError, _embedding_model


class PolicyRAGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Chroma's Windows Rust backend rejects generated temporary names with
        # punctuation. This is a fixed, ignored test-only store, separate from
        # the real development collection in backend/rag_store.
        cls.temp_dir = "backend/ragtest"
        Path(cls.temp_dir).mkdir(parents=True, exist_ok=True)
        cls.settings = get_settings()
        cls.original_values = {
            "rag_persist_directory": cls.settings.rag_persist_directory,
            "rag_collection_name": cls.settings.rag_collection_name,
            "rag_policy_document_path": cls.settings.rag_policy_document_path,
        }
        cls.settings.rag_persist_directory = cls.temp_dir
        cls.settings.rag_collection_name = "policy_test_collection"
        cls.settings.rag_policy_document_path = "data/policy/Company_Retention_Policy_2026.pdf"

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
        cls.manager = User(email="ragmanager@example.com", password_hash=hash_password("manager-password"), role=UserRole.MANAGER)
        customer_user = User(email="ragcustomer@example.com", password_hash=hash_password("customer-password"), role=UserRole.CUSTOMER)
        cls.customer = Customer(name="RAG Customer", email="ragcustomer@example.com", user=customer_user)
        room = Room(room_number="RAG-1", room_type="standard", price_per_night=Decimal("4500"), capacity=2)
        db.add_all([cls.manager, cls.customer, room])
        db.flush()
        booking = Booking(customer_id=cls.customer.customer_id, room_id=room.room_id, check_in=date(2026, 4, 10), check_out=date(2026, 4, 12), guests=2, total_amount=Decimal("9000"), status=BookingStatus.CANCEL_PENDING)
        db.add(booking)
        db.flush()
        cls.request = RetentionRequest(booking_id=booking.booking_id, customer_id=cls.customer.customer_id, status=RetentionRequestStatus.PENDING)
        db.add(cls.request)
        db.commit()
        cls.manager_id, cls.customer_id, cls.request_id, cls.booking_id = cls.manager.user_id, cls.customer.customer_id, cls.request.request_id, booking.booking_id
        db.close()

        cls.ingestion = PolicyIngestionService(cls.settings)
        cls.first_report = cls.ingestion.ingest_policy()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        for name, value in cls.original_values.items():
            setattr(cls.settings, name, value)

    def test_pdf_chunk_metadata_embeddings_and_idempotency(self):
        pages = self.ingestion.extract_pages()
        self.assertEqual(len(pages), 7)
        self.assertTrue(all(pages))
        chunks = self.ingestion.chunks_from_pages(pages)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0].chunk_id, self.ingestion.chunks_from_pages(pages)[0].chunk_id)
        self.assertTrue(all({"document_name", "page", "chunk_index", "chunk_id"} <= set(c.metadata) for c in chunks))
        vector = _embedding_model(self.settings.rag_embedding_model).encode([chunks[0].text])
        self.assertEqual(vector.shape[1], 384)

        collection = chromadb.PersistentClient(path=self.temp_dir).get_collection(self.settings.rag_collection_name)
        first_count = collection.count()
        second = self.ingestion.ingest_policy()
        self.assertEqual(self.first_report.chunk_count, second.chunk_count)
        self.assertEqual(first_count, collection.count())

    def test_retrieval_validation_and_missing_document_handling(self):
        service = PolicyRAGService(self.settings)
        results = service.retrieve_policy("What retention discount is allowed for a high-risk customer?", top_k=2)
        self.assertEqual(len(results), 2)
        self.assertTrue(all({"text", "source", "page", "chunk_id", "distance"} <= set(row) for row in results))
        self.assertTrue(all(row["source"] == "Company_Retention_Policy_2026.pdf" for row in results))
        self.assertTrue(all(isinstance(row["page"], int) and row["chunk_id"] for row in results))
        self.assertEqual(len(service.retrieve_policy("retention policy", top_k=1)), 1)
        with self.assertRaises(RAGValidationError):
            service.retrieve_policy("   ")

        original_path = self.settings.rag_policy_document_path
        self.settings.rag_policy_document_path = "data/policy/not-present.pdf"
        try:
            with self.assertRaises(RAGError):
                PolicyIngestionService(self.settings).ingest_policy()
        finally:
            self.settings.rag_policy_document_path = original_path

    def test_manager_api_authorization_input_security_and_immutability(self):
        manager_token = create_access_token(self.manager_id, "manager")
        customer = self.Session().get(Customer, self.customer_id)
        customer_token = create_access_token(customer.user_id, "customer")
        headers = {"Authorization": f"Bearer {manager_token}"}
        db = self.Session()
        booking = db.get(Booking, self.booking_id)
        snapshot = (
            booking.status,
            db.get(RetentionRequest, self.request_id).status,
            db.query(Offer).count(),
            db.query(RetentionDecision).count(),
            db.query(AuditLog).count(),
        )
        db.close()

        endpoint = "/api/v1/admin/rag/policy-search"
        self.assertEqual(self.client.post(endpoint, json={"query": "retention"}).status_code, 401)
        self.assertEqual(self.client.post(endpoint, headers={"Authorization": f"Bearer {customer_token}"}, json={"query": "retention"}).status_code, 403)
        response = self.client.post(endpoint, headers=headers, json={"query": "What are the retention conditions?", "top_k": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 2)
        self.assertEqual(self.client.post(endpoint, headers=headers, json={"query": "x", "path": "C:/Windows/win.ini"}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, headers=headers, json={"query": "   "}).status_code, 422)

        after = self.Session()
        booking = after.get(Booking, self.booking_id)
        self.assertEqual(snapshot, (
            booking.status,
            after.get(RetentionRequest, self.request_id).status,
            after.query(Offer).count(),
            after.query(RetentionDecision).count(),
            after.query(AuditLog).count(),
        ))
        after.close()
