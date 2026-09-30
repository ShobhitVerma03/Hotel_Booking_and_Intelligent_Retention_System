from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from backend.app.api.dependencies import require_manager
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.database.session import get_db
from backend.app.models.entities import AuditLog, Booking, Customer, Offer, RetentionRequest, Room
from backend.app.models.enums import BookingStatus, RetentionRequestStatus, RoomStatus
from backend.app.schemas.admin import Dashboard, Page
from backend.app.schemas.rag import PolicySearchRequest, PolicySearchResponse
from backend.app.services.rag import PolicyRAGService, RAGError, RAGValidationError
from backend.app.schemas.workflow import RetentionWorkflowResponse
from backend.app.schemas.nl_sql import NLQueryRequest, NLQueryResponse
from backend.app.services.nl_sql import NLAnalyticsError, NLAnalyticsService
from backend.app.schemas.retention import (
    CancellationResolutionCreate, CancellationResolutionResponse,
    ManagerDecisionCreate, ManagerDecisionResponse,
)
from backend.app.services.cancellation_resolution import resolve_cancellation_request
from backend.app.services.retention_decision import decide_retention_request
from backend.app.workflows.retention import RetentionWorkflowError, RetentionWorkflowService
from backend.ml.features import customer_features
from backend.ml.predict import predict

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_manager)])


@router.post("/nl-sql/query", response_model=NLQueryResponse)
def nl_sql_query(payload: NLQueryRequest, manager=Depends(require_manager), db: Session = Depends(get_db)) -> dict:
    """Manager-only, bounded read-only analytics; SQL is AST-validated before execution."""

    try:
        return NLAnalyticsService(db, manager.user_id).query(payload.question)
    except NLAnalyticsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/rag/policy-search", response_model=PolicySearchResponse)
def policy_search(payload: PolicySearchRequest) -> dict:
    """Manager-only inspection endpoint for retrieval-only policy context."""

    try:
        results = PolicyRAGService().retrieve_policy(payload.query, payload.top_k)
    except RAGValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RAGError as exc:
        raise HTTPException(status_code=503, detail="Policy retrieval is temporarily unavailable") from exc
    return {"query": payload.query, "results": results}


@router.post("/retention-requests/{request_id}/recommendation", response_model=RetentionWorkflowResponse)
def retention_recommendation(request_id: int, manager=Depends(require_manager), db: Session = Depends(get_db)) -> dict:
    """Produce/retrieve a checkpointed recommendation; never a manager decision."""

    if not db.get(RetentionRequest, request_id):
        raise HTTPException(status_code=404, detail="Retention request not found")
    try:
        state = RetentionWorkflowService(db, manager.user_id).run(request_id)
    except RetentionWorkflowError as exc:
        raise HTTPException(status_code=503, detail="Retention workflow is temporarily unavailable") from exc
    recommendation = state.get("recommendation")
    sources = recommendation.get("policy_sources", []) if recommendation else []
    return {
        "request_id": request_id,
        "workflow_status": state.get("workflow_status"),
        "risk_score": state.get("risk_score"),
        "risk_category": state.get("risk_category"),
        "recommendation": recommendation,
        "policy_sources": sources,
        "error": state.get("error"),
        "policy_results": state.get("policy_results", []),
    }


@router.post("/retention-requests/{request_id}/decision", response_model=ManagerDecisionResponse)
def retention_manager_decision(
    request_id: int,
    payload: ManagerDecisionCreate,
    manager=Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Persist a manager's final approve/modify/reject decision; never a customer decision."""

    decision, workflow_status = decide_retention_request(db, request_id, manager, payload)
    request = db.get(RetentionRequest, request_id)
    final = decision.final_offer or {}
    return {
        "decision_id": decision.decision_id,
        "request_id": request_id,
        "action": decision.action.value,
        "request_status": request.status.value,
        "workflow_status": workflow_status,
        "final_offer": final.get("final_customer_offer"),
    }


@router.post("/cancellation-requests/{request_id}/resolution", response_model=CancellationResolutionResponse)
def cancellation_resolution(
    request_id: int,
    payload: CancellationResolutionCreate,
    manager=Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Persist a manager's direct cancellation approval or decline.

    This endpoint does not generate or approve a retention offer.  Managers use
    the existing recommendation/decision endpoints when they choose the
    retention branch instead.
    """

    request = resolve_cancellation_request(db, request_id, manager, payload)
    return {
        "request_id": request.request_id,
        "request_status": request.status.value,
        "booking_status": request.booking.status.value,
        "action": payload.action.value,
    }


def page_result(query, page: int, page_size: int, serialize):
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=[serialize(row) for row in rows], page=page, page_size=page_size, total=total)


def booking_data(b: Booking) -> dict:
    offer = next((o for o in b.offers if o.offer_type == "first_time_welcome"), None)
    base = b.room.price_per_night * (b.check_out - b.check_in).days
    return {"booking_id": b.booking_id, "customer": {"customer_id": b.customer_id, "name": b.customer.name, "email": b.customer.email}, "room": {"room_id": b.room_id, "room_number": b.room.room_number, "room_type": b.room.room_type}, "check_in": b.check_in, "check_out": b.check_out, "status": b.status.value, "base_amount": base, "discount": offer.discount if offer else None, "final_amount": b.total_amount, "created_at": b.created_at}


def request_data(r: RetentionRequest) -> dict:
    return {"request_id": r.request_id, "booking_id": r.booking_id, "request_kind": r.request_kind, "booking_status": r.booking.status.value, "customer": {"customer_id": r.customer_id, "name": r.customer.name, "email": r.customer.email}, "booking_dates": {"check_in": r.booking.check_in, "check_out": r.booking.check_out}, "reason": r.reason, "status": r.status.value, "created_at": r.created_at}


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db)):
    booked = db.query(Booking).filter(Booking.status != BookingStatus.CANCELLED).count()
    pending = db.query(RetentionRequest).filter(RetentionRequest.status.in_([RetentionRequestStatus.PENDING, RetentionRequestStatus.IN_REVIEW, RetentionRequestStatus.OFFERED])).count()
    return Dashboard(customers={"total": db.query(Customer).count()}, rooms={"total": db.query(Room).count(), "available": db.query(Room).filter(Room.status == RoomStatus.AVAILABLE).count(), "booked": booked}, bookings={"total": db.query(Booking).count(), "active": booked, "cancelled": db.query(Booking).filter(Booking.status == BookingStatus.CANCELLED).count(), "confirmed": db.query(Booking).filter(Booking.status == BookingStatus.CONFIRMED).count()}, retention={"pending_cancellations": db.query(Booking).filter(Booking.status == BookingStatus.CANCEL_PENDING).count(), "pending_retention_requests": pending})


@router.get("/customers", response_model=Page)
def customers(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Customer)
    if q: query = query.filter(or_(Customer.name.ilike(f"%{q}%"), Customer.email.ilike(f"%{q.lower()}%")))
    return page_result(query.order_by(Customer.created_at.desc()), page, page_size, lambda c: {"customer_id": c.customer_id, "name": c.name, "email": c.email, "phone": c.phone, "created_at": c.created_at, "booking_count": len(c.bookings)})


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: int, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c: raise HTTPException(404, "Customer not found")
    return {"customer_id": c.customer_id, "name": c.name, "email": c.email, "phone": c.phone, "created_at": c.created_at, "bookings": [booking_data(b) for b in c.bookings], "total_bookings": len(c.bookings), "active_bookings": sum(b.status != BookingStatus.CANCELLED for b in c.bookings), "cancelled_bookings": sum(b.status == BookingStatus.CANCELLED for b in c.bookings), "retention_requests": [request_data(r) for r in c.retention_requests], "offers": [{"offer_id": o.offer_id, "type": o.offer_type, "discount": o.discount, "status": o.status.value} for o in c.offers]}

@router.get('/customers/{customer_id}/risk')
def customer_risk(customer_id:int, db:Session=Depends(get_db)):
    c=db.get(Customer,customer_id)
    if not c: raise HTTPException(404,'Customer not found')
    return {'customer_id':customer_id,**predict(customer_features(db,c))}


@router.get("/bookings", response_model=Page)
def bookings(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status: BookingStatus | None = None, customer_id: int | None = None, room_id: int | None = None, check_in: date | None = None, check_out: date | None = None, db: Session = Depends(get_db)):
    query = db.query(Booking)
    if status: query = query.filter(Booking.status == status)
    if customer_id: query = query.filter(Booking.customer_id == customer_id)
    if room_id: query = query.filter(Booking.room_id == room_id)
    if check_in: query = query.filter(Booking.check_in >= check_in)
    if check_out: query = query.filter(Booking.check_out <= check_out)
    return page_result(query.order_by(Booking.created_at.desc()), page, page_size, booking_data)


@router.get("/bookings/{booking_id}")
def booking_detail(booking_id: int, db: Session = Depends(get_db)):
    b = db.get(Booking, booking_id)
    if not b: raise HTTPException(404, "Booking not found")
    data = booking_data(b); data["retention_requests"] = [request_data(r) for r in b.retention_requests]; data["audit_events"] = audit_for(db, "booking", booking_id); return data


@router.get("/rooms", response_model=Page)
def rooms(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), room_type: str | None = None, status: RoomStatus | None = None, capacity: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    query = db.query(Room)
    if room_type: query = query.filter(Room.room_type == room_type)
    if status: query = query.filter(Room.status == status)
    if capacity: query = query.filter(Room.capacity >= capacity)
    return page_result(query.order_by(Room.room_number), page, page_size, lambda r: {"room_id": r.room_id, "room_number": r.room_number, "room_type": r.room_type, "price_per_night": r.price_per_night, "capacity": r.capacity, "status": r.status.value})


@router.get("/rooms/{room_id}")
def room_detail(room_id: int, db: Session = Depends(get_db)):
    r = db.get(Room, room_id)
    if not r: raise HTTPException(404, "Room not found")
    return {"room_id": r.room_id, "room_number": r.room_number, "room_type": r.room_type, "price_per_night": r.price_per_night, "capacity": r.capacity, "status": r.status.value, "bookings": [booking_data(b) for b in r.bookings]}


@router.get("/cancellation-requests", response_model=Page)
@router.get("/retention-requests", response_model=Page)
def retention_requests(http_request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status: RetentionRequestStatus | None = None, customer_id: int | None = None, booking_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(RetentionRequest)
    if "/cancellation-requests" in http_request.url.path:
        query = query.filter(RetentionRequest.request_kind == "cancellation")
    if status: query = query.filter(RetentionRequest.status == status)
    if customer_id: query = query.filter(RetentionRequest.customer_id == customer_id)
    if booking_id: query = query.filter(RetentionRequest.booking_id == booking_id)
    return page_result(query.order_by(RetentionRequest.created_at.desc()), page, page_size, request_data)


@router.get("/cancellation-requests/{request_id}")
@router.get("/retention-requests/{request_id}")
def retention_detail(request_id: int, db: Session = Depends(get_db)):
    r = db.get(RetentionRequest, request_id)
    if not r: raise HTTPException(404, "Retention request not found")
    data = request_data(r); data["workflow"] = r.workflow_state; data["offers"] = [{"offer_id": o.offer_id, "type": o.offer_type, "discount": o.discount} for o in r.booking.offers]; data["decisions"] = [{"decision_id": d.decision_id, "action": d.action.value, "reason": d.reason, "created_at": d.created_at} for d in r.decisions]; data["audit_events"] = audit_for(db, "retention_request", request_id); return data

@router.get('/retention-requests/{request_id}/risk')
def retention_risk(request_id:int, db:Session=Depends(get_db)):
    r=db.get(RetentionRequest,request_id)
    if not r: raise HTTPException(404,'Retention request not found')
    return {'request_id':request_id,'customer_id':r.customer_id,**predict(customer_features(db,r.customer,r.booking))}


def audit_for(db: Session, entity_type: str, entity_id: int):
    return [{"audit_log_id": a.audit_log_id, "action": a.event_type, "entity_type": a.entity_type, "entity_id": a.entity_id, "timestamp": a.created_at, "metadata": a.details} for a in db.query(AuditLog).filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id)).order_by(AuditLog.created_at.desc()).all()]


@router.get("/audit-logs", response_model=Page)
def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), entity_type: str | None = None, entity_id: str | None = None, action: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if entity_type: query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id: query = query.filter(AuditLog.entity_id == entity_id)
    if action: query = query.filter(AuditLog.event_type == action)
    if start_date: query = query.filter(AuditLog.created_at >= start_date)
    if end_date: query = query.filter(AuditLog.created_at <= end_date)
    return page_result(query.order_by(AuditLog.created_at.desc()), page, page_size, lambda a: {"audit_log_id": a.audit_log_id, "action": a.event_type, "entity_type": a.entity_type, "entity_id": a.entity_id, "timestamp": a.created_at, "metadata": a.details})


@router.get("/search")
def search(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(or_(Customer.name.ilike(f"%{q}%"), Customer.email.ilike(f"%{q}%"))).limit(20).all()
    bookings = db.query(Booking).filter(Booking.booking_id == int(q)).all() if q.isdigit() else []
    return {"customers": [{"customer_id": c.customer_id, "name": c.name, "email": c.email} for c in customers], "bookings": [{"booking_id": b.booking_id, "status": b.status.value} for b in bookings]}
