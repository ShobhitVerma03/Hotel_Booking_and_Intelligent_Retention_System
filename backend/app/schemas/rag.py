"""Request and response contracts for internal policy retrieval."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolicySearchRequest(BaseModel):
    """A manager's policy-context search; no client-controlled file inputs."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query must not be empty")
        return value


class PolicySearchResult(BaseModel):
    text: str
    source: str
    page: int
    chunk_id: str
    distance: float | None = None


class PolicySearchResponse(BaseModel):
    query: str
    results: list[PolicySearchResult]
