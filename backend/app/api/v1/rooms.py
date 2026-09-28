from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from backend.app.database.session import get_db
from backend.app.models.entities import Room
from backend.app.models.enums import RoomStatus
from backend.app.schemas.room import RoomResponse
from backend.app.services.booking import available_rooms

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomResponse])
def list_rooms(available_only: bool = False, db: Session = Depends(get_db)) -> list[Room]:
    query = db.query(Room)
    if available_only:
        query = query.filter(Room.status == RoomStatus.AVAILABLE)
    return query.order_by(Room.room_number).all()


@router.get("/available", response_model=list[RoomResponse])
def list_available_rooms(check_in: date, check_out: date, capacity: int | None = Query(None, ge=1), room_type: str | None = None, db: Session = Depends(get_db)) -> list[Room]:
    if check_out <= check_in:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="check_out must be after check_in")
    return available_rooms(db, check_in, check_out, capacity, room_type)
