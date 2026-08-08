"""Vacancy schemas used before and after AI extraction."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class ApplicationStatus(StrEnum):
    """Tracked application lifecycle status."""

    DISCOVERED = "discovered"
    SCREENED = "screened"
    APPROVED = "approved"
    REJECTED = "rejected"
    PREPARING = "preparing"
    AWAITING_REVIEW = "awaiting_review"
    READY_TO_SEND = "ready_to_send"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    UNSUCCESSFUL = "unsuccessful"
    WITHDRAWN = "withdrawn"


class EmploymentMode(StrEnum):
    """Vacancy work arrangement."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class RequirementLevel(StrEnum):
    """Whether a vacancy skill is required or preferred."""

    REQUIRED = "required"
    PREFERRED = "preferred"


class SkillRequirement(BaseModel):
    """A skill requirement extracted from vacancy text."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    level: RequirementLevel
    evidence_text: str | None = None


class Vacancy(BaseModel):
    """Structured internship vacancy information."""

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=200)
    role_title: str = Field(min_length=1, max_length=200)
    location: str | None = None
    employment_mode: EmploymentMode = EmploymentMode.UNKNOWN
    application_email: EmailStr | None = None
    application_url: HttpUrl | None = None
    deadline: date | None = None

    responsibilities: list[str] = Field(default_factory=list)
    skills: list[SkillRequirement] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    eligibility_requirements: list[str] = Field(default_factory=list)

    internship_start: date | None = None
    internship_end: date | None = None
    minimum_duration_weeks: int | None = Field(default=None, ge=1, le=104)

    source_text: str = Field(min_length=20)
    extraction_warnings: list[str] = Field(default_factory=list)

    def normalized_required_skills(self) -> set[str]:
        """Return lowercase required skill names."""

        return {
            skill.name.strip().casefold()
            for skill in self.skills
            if skill.level == RequirementLevel.REQUIRED and skill.name.strip()
        }

    def normalized_preferred_skills(self) -> set[str]:
        """Return lowercase preferred skill names."""

        return {
            skill.name.strip().casefold()
            for skill in self.skills
            if skill.level == RequirementLevel.PREFERRED and skill.name.strip()
        }
