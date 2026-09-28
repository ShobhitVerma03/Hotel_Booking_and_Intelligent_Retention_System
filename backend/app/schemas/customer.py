from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from backend.app.schemas.common import TimestampResponse


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=50)


class CustomerIdentify(CustomerCreate):
    pass


class CustomerResponse(TimestampResponse):
    customer_id: int
    user_id: Optional[int]
    name: str
    email: EmailStr
    phone: Optional[str]
    loyalty_tier: str


class CustomerIdentificationResponse(BaseModel):
    customer: CustomerResponse
    customer_type: str
