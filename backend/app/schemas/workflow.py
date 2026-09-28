"""Public contracts for retention-workflow recommendations."""

from pydantic import BaseModel, Field


class PolicySource(BaseModel):
    source: str
    page: int
    chunk_id: str


class RetentionRecommendation(BaseModel):
    action: str
    offer_type: str | None = None
    discount_percentage: float | None = Field(default=None, ge=0, le=100)
    reason: str
    risk_category: str
    policy_sources: list[PolicySource]
    requires_manager_review: bool = True
    policy_limit_percentage: float | None = Field(default=None, ge=0, le=100)
    policy_conflict: bool = False


class RetentionWorkflowResponse(BaseModel):
    request_id: int
    workflow_status: str
    risk_score: float | None = None
    risk_category: str | None = None
    recommendation: RetentionRecommendation | None = None
    policy_sources: list[PolicySource] = []
    error: str | None = None
