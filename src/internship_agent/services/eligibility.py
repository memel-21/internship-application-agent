"""Deterministic hard eligibility checks."""

from dataclasses import dataclass, field

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.vacancy import Vacancy


@dataclass(frozen=True)
class EligibilityResult:
    """Result of hard eligibility checks."""

    is_eligible: bool
    reasons: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)


def check_eligibility(
    candidate: CandidateProfile, vacancy: Vacancy, *, current_year: int
) -> EligibilityResult:
    """Evaluate deterministic hard rejection conditions."""

    reasons: list[str] = []
    missing_information: list[str] = []

    if not candidate.verified:
        reasons.append("Candidate profile is not marked as verified.")

    if (
        vacancy.minimum_duration_weeks
        and candidate.internship.duration_weeks < vacancy.minimum_duration_weeks
    ):
        reasons.append("Candidate internship availability is shorter than the minimum duration.")

    if vacancy.internship_start and candidate.internship.start_date > vacancy.internship_start:
        reasons.append("Candidate internship starts after the vacancy start date.")

    if vacancy.internship_end and candidate.internship.end_date < vacancy.internship_end:
        reasons.append("Candidate internship ends before the vacancy end date.")

    if _requires_current_student(vacancy) and candidate.graduation_year is None:
        missing_information.append("Explicit graduation year is missing.")
    elif (
        _requires_current_student(vacancy)
        and candidate.graduation_year is not None
        and candidate.graduation_year < current_year
    ):
        reasons.append("Vacancy requires a current student, but candidate graduation year is past.")

    if vacancy.education_requirements:
        normalized_degree = candidate.degree.casefold()
        normalized_field = candidate.field_of_study.casefold()
        degree_match = any(
            eligible.casefold() in normalized_degree or eligible.casefold() in normalized_field
            for eligible in vacancy.education_requirements
        )
        if not degree_match:
            reasons.append("Candidate degree or field of study does not match eligible degrees.")

    if _requires_work_authorisation(vacancy):
        authorized_countries = candidate.authorized_countries()
        if not authorized_countries:
            missing_information.append("Explicit work authorization information is missing.")
        elif not _authorization_matches(vacancy, authorized_countries):
            reasons.append("Candidate lacks explicit work authorization for the vacancy country.")

    return EligibilityResult(
        is_eligible=not reasons and not missing_information,
        reasons=reasons,
        missing_information=missing_information,
    )


def _requires_current_student(vacancy: Vacancy) -> bool:
    return any(
        "current student" in requirement.casefold()
        for requirement in vacancy.eligibility_requirements
    )


def _requires_work_authorisation(vacancy: Vacancy) -> bool:
    authorization_terms = ("work authorisation", "work authorization", "authorised", "authorized")
    return any(
        any(term in requirement.casefold() for term in authorization_terms)
        for requirement in vacancy.eligibility_requirements
    )


def _authorization_matches(vacancy: Vacancy, authorized_countries: set[str]) -> bool:
    requirement_text = " ".join(vacancy.eligibility_requirements).casefold()
    return any(country in requirement_text for country in authorized_countries)
