"""Manager decision contracts for the persistent retention HITL workflow."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ManagerDecisionAction(StrEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"


class CancellationResolutionAction(StrEnum):
    """A manager's direct cancellation resolution, distinct from an offer decision."""

    APPROVE_CANCELLATION = "approve_cancellation"
    DECLINE_CANCELLATION = "decline_cancellation"


class CancellationResolutionCreate(BaseModel):
    action: CancellationResolutionAction
    comment: str | None = Field(default=None, max_length=2000)


class CancellationResolutionResponse(BaseModel):
    request_id: int
    request_status: str
    booking_status: str
    action: CancellationResolutionAction


class ManagerOfferModification(BaseModel):
    """A manager-provided final customer offer, validated against workflow policy."""

    offer_type: str = Field(min_length=1, max_length=100)
    discount_percentage: float | None = Field(default=None, ge=0, le=100)
    description: str = Field(min_length=1, max_length=2000)


class ManagerDecisionCreate(BaseModel):
    action: ManagerDecisionAction
    comment: str | None = Field(default=None, max_length=2000)
    modified_offer: ManagerOfferModification | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ManagerDecisionCreate":
        if self.action is ManagerDecisionAction.MODIFY and self.modified_offer is None:
            raise ValueError("modified_offer is required for a modify decision")
        if self.action is not ManagerDecisionAction.MODIFY and self.modified_offer is not None:
            raise ValueError("modified_offer is only allowed for a modify decision")
        return self


class ManagerDecisionResponse(BaseModel):
    decision_id: int
    request_id: int
    action: ManagerDecisionAction
    request_status: str
    workflow_status: str
    final_offer: dict | None = None
