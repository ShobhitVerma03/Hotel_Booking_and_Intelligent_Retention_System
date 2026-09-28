import os
os.environ.setdefault('JWT_SECRET_KEY','test-only-secret-with-at-least-thirty-two-characters')
import unittest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.database.base import Base
from backend.app.database.session import get_db
from backend.app.main import app
from backend.app.models.entities import Customer, Room, User, Booking, RetentionRequest, Offer, RetentionDecision, AuditLog
from backend.app.models.enums import UserRole, BookingStatus, RetentionRequestStatus
from backend.app.services.auth import hash_password, create_access_token
from backend.ml.features import customer_features
from backend.ml.predict import category, load_model, predict
from backend.app.core.config import get_settings
import backend.app.models

class MlTests(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool); Base.metadata.create_all(c.e); c.S=sessionmaker(bind=c.e)
  def dep():
   d=c.S()
   try: yield d
   finally: d.close()
  app.dependency_overrides[get_db]=dep; c.client=TestClient(app)
  d=c.S(); c.m=User(email='mlmanager@example.com',password_hash=hash_password('manager-password'),role=UserRole.MANAGER); c.u=User(email='mlcustomer@example.com',password_hash=hash_password('customer-password'),role=UserRole.CUSTOMER); c.c=Customer(name='ML Customer',email='mlcustomer@example.com',user=c.u); r=Room(room_number='ML1',room_type='standard',price_per_night=Decimal('5000'),capacity=2); d.add_all([c.m,c.c,r]);d.flush()
  for i in range(2): d.add(Booking(customer_id=c.c.customer_id,room_id=r.room_id,check_in=date(2026,1+i,1),check_out=date(2026,1+i,3),guests=2,total_amount=Decimal('10000'),status=BookingStatus.COMPLETED))
  d.flush(); b=d.query(Booking).first(); c.req=RetentionRequest(booking_id=b.booking_id,customer_id=c.c.customer_id,status=RetentionRequestStatus.PENDING);d.add(c.req);d.commit();d.refresh(c.c);d.refresh(c.req);c.mid=c.m.user_id;c.cid=c.c.customer_id;c.rid=c.req.request_id;d.close()
 @classmethod
 def tearDownClass(c): app.dependency_overrides.clear();Base.metadata.drop_all(c.e)
 def test_features_thresholds_and_cold_start(self):
  d=self.S(); f=customer_features(d,d.get(Customer,self.cid));self.assertEqual(list(f),load_model()[1]['features']);self.assertTrue(0<=predict(f)['risk_score']<=1);s=get_settings();self.assertEqual(category(s.ml_low_risk_threshold-.01),'LOW');self.assertEqual(category(s.ml_low_risk_threshold),'MEDIUM');self.assertEqual(category(s.ml_high_risk_threshold),'HIGH'); cold=Customer(name='Cold',email='cold@example.com',user=User(email='cold@example.com',role=UserRole.CUSTOMER));d.add(cold);d.commit();self.assertEqual(predict(customer_features(d,cold))['risk_category'],'UNKNOWN');d.close()
 def test_risk_authorization_and_immutability(self):
  mt=create_access_token(self.mid,'manager'); ct=create_access_token(self.S().get(Customer,self.cid).user_id,'customer');h={'Authorization':'Bearer '+mt}; before=self.S(); b=before.query(Booking).first(); snapshot=(b.status,before.get(RetentionRequest,self.rid).status,before.query(Offer).count(),before.query(RetentionDecision).count(),before.query(AuditLog).count());before.close()
  self.assertEqual(self.client.get(f'/api/v1/admin/customers/{self.cid}/risk').status_code,401);self.assertEqual(self.client.get(f'/api/v1/admin/customers/{self.cid}/risk',headers={'Authorization':'Bearer '+ct}).status_code,403);self.assertEqual(self.client.get(f'/api/v1/admin/customers/{self.cid}/risk',headers=h).status_code,200);self.assertEqual(self.client.get(f'/api/v1/admin/retention-requests/{self.rid}/risk',headers=h).status_code,200);self.assertEqual(self.client.get('/api/v1/admin/customers/9999/risk',headers=h).status_code,404);after=self.S();b=after.query(Booking).first();self.assertEqual(snapshot,(b.status,after.get(RetentionRequest,self.rid).status,after.query(Offer).count(),after.query(RetentionDecision).count(),after.query(AuditLog).count()));after.close()
 def test_missing_model_is_controlled(self):
  s=get_settings();old=s.ml_model_path;s.ml_model_path='backend/ml/artifacts/missing.joblib';load_model.cache_clear()
  try:
   with self.assertRaises(RuntimeError): load_model()
  finally: s.ml_model_path=old;load_model.cache_clear()
