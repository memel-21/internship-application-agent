"""Deterministic vacancy match scoring."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.vacancy import EmploymentMode, Vacancy
from internship_agent.services.eligibility import check_eligibility


class Recommendation(StrEnum):
    """Deterministic recommendation for a vacancy."""

    APPLY = "apply"
    REVIEW = "review"
    SKIP = "skip"


class ScoreBreakdown(BaseModel):
    """Weighted deterministic score components."""

    model_config = ConfigDict(extra="forbid")

    role_alignment: float = Field(ge=0, le=25)
    student_eligibility: float = Field(ge=0, le=15)
    date_compatibility: float = Field(ge=0, le=20)
    required_skills: float = Field(ge=0, le=25)
    location: float = Field(ge=0, le=10)
    preferred_skills: float = Field(ge=0, le=5)

    def total(self) -> float:
        """Return the summed deterministic score."""

        return round(
            self.role_alignment
            + self.student_eligibility
            + self.date_compatibility
            + self.required_skills
            + self.location
            + self.preferred_skills,
            2,
        )


class MatchScore(BaseModel):
    """Deterministic candidate-to-vacancy assessment."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=100)
    recommendation: Recommendation
    hard_rejected: bool
    hard_rejection_reasons: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown
    matched_required_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)


def calculate_match_score(
    candidate: CandidateProfile, vacancy: Vacancy, *, current_year: int
) -> MatchScore:
    """Calculate a deterministic match score from eligibility, skills, dates, and location."""

    eligibility = check_eligibility(candidate, vacancy, current_year=current_year)
    candidate_skills = candidate.normalized_skills()
    required = vacancy.normalized_required_skills()
    preferred = vacancy.normalized_preferred_skills()

    matched_required = sorted(required & candidate_skills)
    missing_required = sorted(required - candidate_skills)
    matched_preferred = sorted(preferred & candidate_skills)
    missing_preferred = sorted(preferred - candidate_skills)

    hard_rejection_reasons = [*eligibility.reasons]
    if missing_required:
        hard_rejection_reasons.append("Candidate is missing one or more required skills.")

    hard_rejected = bool(hard_rejection_reasons or eligibility.missing_information)
    warnings = _warnings(vacancy, eligibility.missing_information)
    gaps = _gaps(missing_required, missing_preferred)
    strengths = _strengths(candidate, vacancy, matched_required, matched_preferred)

    if hard_rejected:
        breakdown = ScoreBreakdown(
            role_alignment=0,
            student_eligibility=0,
            date_compatibility=0,
            required_skills=0,
            location=0,
            preferred_skills=0,
        )
        return MatchScore(
            score=0,
            recommendation=Recommendation.SKIP,
            hard_rejected=True,
            hard_rejection_reasons=[*hard_rejection_reasons, *eligibility.missing_information],
            strengths=strengths,
            gaps=gaps,
            warnings=warnings,
            score_breakdown=breakdown,
            matched_required_skills=matched_required,
            missing_required_skills=missing_required,
            matched_preferred_skills=matched_preferred,
        )

    breakdown = ScoreBreakdown(
        role_alignment=_role_alignment_score(candidate, vacancy),
        student_eligibility=15,
        date_compatibility=_date_score(candidate, vacancy),
        required_skills=_skill_score(matched_required, required, weight=25),
        location=_location_score(candidate, vacancy),
        preferred_skills=_skill_score(matched_preferred, preferred, weight=5),
    )
    score = breakdown.total()

    return MatchScore(
        score=score,
        recommendation=_recommendation(score, candidate.preferences.minimum_match_score),
        hard_rejected=False,
        hard_rejection_reasons=[],
        strengths=strengths,
        gaps=gaps,
        warnings=warnings,
        score_breakdown=breakdown,
        matched_required_skills=matched_required,
        missing_required_skills=missing_required,
        matched_preferred_skills=matched_preferred,
    )


def _skill_score(matched: list[str], required: set[str], *, weight: int) -> float:
    if not required:
        return float(weight)
    return round(weight * (len(matched) / len(required)), 2)


def _role_alignment_score(candidate: CandidateProfile, vacancy: Vacancy) -> float:
    vacancy_tokens = _tokens(vacancy.role_title)
    if not vacancy_tokens:
        return 0
    best_overlap = 0.0
    for role in candidate.preferences.target_roles:
        role_tokens = _tokens(role)
        if not role_tokens:
            continue
        best_overlap = max(best_overlap, len(vacancy_tokens & role_tokens) / len(role_tokens))
    return round(25 * best_overlap, 2)


def _date_score(candidate: CandidateProfile, vacancy: Vacancy) -> float:
    if vacancy.internship_start and candidate.internship.start_date > vacancy.internship_start:
        return 0
    if vacancy.internship_end and candidate.internship.end_date < vacancy.internship_end:
        return 0
    if (
        vacancy.minimum_duration_weeks
        and candidate.internship.duration_weeks < vacancy.minimum_duration_weeks
    ):
        return 0
    return 20


def _location_score(candidate: CandidateProfile, vacancy: Vacancy) -> float:
    if vacancy.employment_mode in {EmploymentMode.REMOTE, EmploymentMode.HYBRID}:
        return 10
    if vacancy.location is None:
        return 0
    normalized_location = vacancy.location.casefold()
    return (
        10
        if any(
            place.casefold() in normalized_location
            for place in candidate.preferences.preferred_locations
        )
        else 0
    )


def _recommendation(score: float, minimum_match_score: int) -> Recommendation:
    if score >= minimum_match_score:
        return Recommendation.APPLY
    if score >= 50:
        return Recommendation.REVIEW
    return Recommendation.SKIP


def _strengths(
    candidate: CandidateProfile,
    vacancy: Vacancy,
    matched_required: list[str],
    matched_preferred: list[str],
) -> list[str]:
    strengths: list[str] = []
    for skill in [*matched_required, *matched_preferred]:
        strengths.append(f"Verified {skill} match")
    if _date_score(candidate, vacancy) == 20:
        strengths.append("Internship dates appear compatible")
    return strengths


def _gaps(missing_required: list[str], missing_preferred: list[str]) -> list[str]:
    return [
        *[f"No verified {skill} evidence" for skill in missing_required],
        *[f"No verified {skill} evidence" for skill in missing_preferred],
    ]


def _warnings(vacancy: Vacancy, missing_information: list[str]) -> list[str]:
    warnings = list(missing_information)
    requirement_text = " ".join(vacancy.eligibility_requirements).casefold()
    if (
        "work authorisation" not in requirement_text
        and "work authorization" not in requirement_text
    ):
        warnings.append("Work-authorisation requirement was not stated")
    return warnings


def _tokens(value: str) -> set[str]:
    ignored = {"intern", "internship", "and", "or", "the", "a", "an"}
    return {
        token
        for token in value.casefold().replace("/", " ").replace("-", " ").split()
        if token and token not in ignored
    }
