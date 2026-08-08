"""Candidate profile schemas."""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PersonalProfile(BaseModel):
    """Personal candidate details that must not be inferred."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1)
    email: str | None = None
    phone: str | None = None
    location: str = Field(min_length=1)
    nationality: str | None = None
    work_authorisation: str | None = None


class EducationProfile(BaseModel):
    """Verified education details."""

    model_config = ConfigDict(extra="forbid")

    institution: str = Field(min_length=1)
    programme: str = Field(min_length=1)
    cgpa: float = Field(ge=0)
    cgpa_scale: float = Field(gt=0)
    academic_highlights: list[str] = Field(default_factory=list)
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)


class InternshipAvailability(BaseModel):
    """Candidate internship availability window."""

    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    duration_weeks: int = Field(gt=0)
    availability_notes: str = Field(min_length=1)


class Preferences(BaseModel):
    """Candidate application preferences."""

    model_config = ConfigDict(extra="forbid")

    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    minimum_match_score: int = Field(ge=0, le=100)


class SkillSet(BaseModel):
    """Candidate skills grouped by category."""

    model_config = ConfigDict(extra="forbid")

    programming: list[str] = Field(default_factory=list)
    ai_and_data: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    def all_skills(self) -> list[str]:
        """Return all skills as a flat list."""

        return [*self.programming, *self.ai_and_data, *self.tools]


class CandidateDocuments(BaseModel):
    """Paths to candidate source documents."""

    model_config = ConfigDict(extra="forbid")

    master_resume_docx: Path
    master_resume_pdf: Path
    academic_transcript: Path
    university_letter: Path
    project_evidence: Path


class ApprovalSettings(BaseModel):
    """Human approval requirements for application actions."""

    model_config = ConfigDict(extra="forbid")

    required_before_email: bool
    required_before_submission: bool
    allow_automatic_submission: bool


class EvidenceFile(BaseModel):
    """Approved source file that can support candidate claims."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    path: Path
    description: str = Field(min_length=1)
    approved: bool = False


class Experience(BaseModel):
    """Verified candidate experience."""

    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """Verified candidate profile loaded from local JSON."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    personal: PersonalProfile
    education: EducationProfile
    internship: InternshipAvailability
    preferences: Preferences
    skills: SkillSet
    documents: CandidateDocuments
    approval: ApprovalSettings
    evidence_files: list[EvidenceFile] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        """Return the candidate's full name."""

        return self.personal.full_name

    @property
    def email(self) -> str | None:
        """Return the candidate's email when explicitly provided."""

        return self.personal.email

    @property
    def university(self) -> str:
        """Return the candidate's university."""

        return self.education.institution

    @property
    def degree(self) -> str:
        """Return the candidate's degree or programme."""

        return self.education.programme

    @property
    def field_of_study(self) -> str:
        """Return the candidate's field of study for deterministic matching."""

        return self.education.programme

    @property
    def graduation_year(self) -> int | None:
        """Return graduation year only when explicitly present."""

        return self.education.graduation_year

    @property
    def verified(self) -> bool:
        """Return whether human approvals forbid automatic submission."""

        return (
            self.approval.required_before_email
            and self.approval.required_before_submission
            and not self.approval.allow_automatic_submission
        )

    def flattened_skills(self) -> list[str]:
        """Return all candidate skills as a flat list."""

        return self.skills.all_skills()

    def normalized_skills(self) -> set[str]:
        """Return lowercase candidate skill names for deterministic matching."""

        return {skill.strip().casefold() for skill in self.flattened_skills() if skill.strip()}

    def authorized_countries(self) -> set[str]:
        """Return explicit work authorisation entries without inference."""

        if self.personal.work_authorisation is None:
            return set()
        return {self.personal.work_authorisation.strip().casefold()}
