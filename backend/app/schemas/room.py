from decimal import Decimal
from backend.app.models.enums import RoomStatus
from backend.app.schemas.common import TimestampResponse


class RoomResponse(TimestampResponse):
    room_id: int
    room_number: str
    room_type: str
    price_per_night: Decimal
    capacity: int
    status: RoomStatus
