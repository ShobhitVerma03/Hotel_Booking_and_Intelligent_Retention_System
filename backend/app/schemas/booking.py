from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator
from backend.app.models.enums import BookingStatus
from backend.app.schemas.common import TimestampResponse


class BookingCreate(BaseModel):
    customer_id: int
    room_id: int
    check_in: date
    check_out: date
    guests: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_stay_dates(self) -> "BookingCreate":
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class BookingResponse(TimestampResponse):
    booking_id: int
    customer_id: int
    room_id: int
    check_in: date
    check_out: date
    guests: int
    total_amount: Decimal
    status: BookingStatus
    room_number: str | None = None
    room_type: str | None = None
    base_amount: Decimal | None = None
    final_amount: Decimal | None = None
    welcome_offer: dict | None = None
    retention_requests: list[dict] = []


class CancellationRequestCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class CancellationRequestResponse(TimestampResponse):
    request_id: int
    booking_id: int
    customer_id: int
    status: str
    reason: str | None


class CustomerRetentionResponse(TimestampResponse):
    request_id: int
    booking_id: int
    customer_id: int
    status: str
    reason: str | None
    booking_status: BookingStatus
    offer: dict | None = None
    request_kind: str = "cancellation"
    message: str = ""


class CustomerBookingHistoryResponse(BaseModel):
    booking_id: int
    room_number: str
    room_type: str
    check_in: date
    check_out: date
    status: BookingStatus
    booking_amount: Decimal
    created_at: datetime
