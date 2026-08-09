"""Generated application content schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeneratedClaim(BaseModel):
    """Internal claim with approved evidence source references."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class GeneratedApplicationContent(BaseModel):
    """Grounded generated content for human review."""

    model_config = ConfigDict(extra="forbid")

    professional_summary: str = Field(min_length=1)
    selected_skills: list[str] = Field(default_factory=list)
    cover_letter: str = Field(min_length=1)
    email_subject: str = Field(min_length=1)
    email_body: str = Field(min_length=1)
    claims: list[GeneratedClaim] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("cover_letter", "email_subject", "email_body")
    @classmethod
    def no_internal_source_refs(cls, value: str) -> str:
        """Prevent internal source markers from leaking into user-facing content."""

        forbidden_markers = ("source_ref", "source:", "[source", "{{")
        lowered = value.casefold()
        if any(marker in lowered for marker in forbidden_markers):
            raise ValueError("user-facing generated content must not expose internal source refs")
        return value
