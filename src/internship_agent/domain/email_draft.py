"""Email draft package schemas."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DraftAttachment(BaseModel):
    """A validated attachment for an application email draft."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    path: Path
    mime_type: str = Field(min_length=1)


class GmailDraftPackage(BaseModel):
    """Gmail-ready draft package that must remain unsent until human review."""

    model_config = ConfigDict(extra="forbid")

    to: EmailStr
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    attachments: list[DraftAttachment] = Field(min_length=1)
