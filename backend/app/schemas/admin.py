from typing import Any
from pydantic import BaseModel, Field


class Page(BaseModel):
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int


class Dashboard(BaseModel):
    customers: dict[str, int]
    rooms: dict[str, int]
    bookings: dict[str, int]
    retention: dict[str, int]


def pagination(page: int = 1, page_size: int = 20) -> tuple[int, int]:
    return page, page_size
