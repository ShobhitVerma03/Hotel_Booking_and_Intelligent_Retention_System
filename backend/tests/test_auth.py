import os
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-production")
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.entities import User
from backend.app.models.enums import UserRole
from backend.app.services.auth import hash_password
import backend.app.models  # noqa


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool); Base.metadata.create_all(cls.engine); cls.Session = sessionmaker(bind=cls.engine)
        def override():
            db = cls.Session()
            try: yield db
            finally: db.close()
        app.dependency_overrides[get_db] = override; cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls): app.dependency_overrides.clear(); Base.metadata.drop_all(cls.engine)

    def test_registration_login_me_and_admin_roles(self):
        reg = self.client.post("/api/v1/auth/register", json={"name":"Auth Guest","email":"auth@example.com","password":"password-123","phone":"555"}); self.assertEqual(reg.status_code, 201); token=reg.json()["access_token"]
        self.assertNotEqual(self.Session().query(User).filter_by(email="auth@example.com").one().password_hash, "password-123")
        self.assertEqual(self.client.post("/api/v1/auth/register", json={"name":"Dup","email":"AUTH@example.com","password":"password-123"}).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/auth/login",json={"email":"auth@example.com","password":"wrong-password"}).status_code,401)
        self.assertEqual(self.client.post("/api/v1/auth/login",json={"email":"auth@example.com","password":"password-123"}).status_code,200)
        me = self.client.get("/api/v1/auth/me",headers={"Authorization":"Bearer "+token}); self.assertEqual(me.status_code,200); self.assertIsNotNone(me.json()["customer_id"])
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code,401)
        self.assertEqual(self.client.get("/api/v1/admin/dashboard").status_code,401)
        self.assertEqual(self.client.get("/api/v1/admin/dashboard",headers={"Authorization":"Bearer "+token}).status_code,403)
        db=self.Session(); manager=User(email="manager@example.com",password_hash=hash_password("manager-password"),role=UserRole.MANAGER); db.add(manager);db.commit();db.close()
        mtoken=self.client.post("/api/v1/auth/login",json={"email":"manager@example.com","password":"manager-password"}).json()["access_token"]
        self.assertEqual(self.client.get("/api/v1/admin/dashboard",headers={"Authorization":"Bearer "+mtoken}).status_code,200)
