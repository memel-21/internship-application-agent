"""Human review decision schemas for application packages."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReviewDecision(StrEnum):
    """Human review outcome for a generated application package."""

    APPROVE = "approve"
    REJECT = "reject"


class ReviewRequest(BaseModel):
    """Human review decision and notes captured before persistence."""

    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    notes: str = Field(default="", max_length=2000)
