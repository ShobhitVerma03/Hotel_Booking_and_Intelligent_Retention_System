"""Public request/response contracts for manager analytics."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class NLQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def non_whitespace_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value.strip()


class NLQueryResponse(BaseModel):
    question: str
    language: str
    intent: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    explanation: str
