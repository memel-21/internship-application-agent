"""Tests for deterministic eligibility and scoring."""

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.vacancy import RequirementLevel, SkillRequirement, Vacancy
from internship_agent.services.eligibility import check_eligibility
from internship_agent.services.scoring import Recommendation, calculate_match_score


def test_eligibility_accepts_matching_candidate(candidate_profile: CandidateProfile) -> None:
    """Eligibility passes when all hard conditions are satisfied."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Data Intern",
        location="Malaysia",
        source_text="Python internship source text with enough detail.",
        education_requirements=["Computer Science"],
        eligibility_requirements=[
            "Must be a current student",
            "Must have work authorisation in Malaysia",
        ],
    )

    result = check_eligibility(candidate_profile, vacancy, current_year=2026)

    assert result.is_eligible is True
    assert result.reasons == []
    assert result.missing_information == []


def test_eligibility_rejects_missing_work_authorization(
    candidate_profile: CandidateProfile,
) -> None:
    """Eligibility does not infer work authorization."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Data Intern",
        location="Singapore",
        source_text="Python internship source text with enough detail.",
        eligibility_requirements=["Must have work authorisation in Singapore"],
    )

    result = check_eligibility(candidate_profile, vacancy, current_year=2026)

    assert result.is_eligible is False
    assert result.reasons == [
        "Candidate lacks explicit work authorization for the vacancy country."
    ]


def test_match_score_full_match(candidate_profile: CandidateProfile) -> None:
    """Full required and preferred skill matches score 100."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Engineering Intern",
        location="Shah Alam",
        source_text="Python SQL ML Streamlit internship source text with enough detail.",
        skills=[
            SkillRequirement(name="Python", level=RequirementLevel.REQUIRED),
            SkillRequirement(name="SQL", level=RequirementLevel.REQUIRED),
            SkillRequirement(name="Machine Learning", level=RequirementLevel.PREFERRED),
            SkillRequirement(name="Streamlit", level=RequirementLevel.PREFERRED),
        ],
    )

    score = calculate_match_score(candidate_profile, vacancy, current_year=2026)

    assert score.score == 100
    assert score.hard_rejected is False
    assert score.recommendation == Recommendation.APPLY
    assert score.score_breakdown.required_skills == 25
    assert score.score_breakdown.location == 10
    assert score.score_breakdown.preferred_skills == 5


def test_match_score_partial_match(candidate_profile: CandidateProfile) -> None:
    """Required skill match with partial preferred skills gets a partial score."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Backend Intern",
        location="Malaysia",
        source_text="Python SQL Docker internship source text with enough detail.",
        skills=[
            SkillRequirement(name="Python", level=RequirementLevel.REQUIRED),
            SkillRequirement(name="SQL", level=RequirementLevel.REQUIRED),
            SkillRequirement(name="Docker", level=RequirementLevel.PREFERRED),
            SkillRequirement(name="Streamlit", level=RequirementLevel.PREFERRED),
        ],
    )

    score = calculate_match_score(candidate_profile, vacancy, current_year=2026)

    assert score.score == 62.5
    assert score.hard_rejected is False
    assert score.recommendation == Recommendation.REVIEW
    assert score.score_breakdown.required_skills == 25
    assert score.score_breakdown.preferred_skills == 2.5
    assert score.matched_preferred_skills == ["streamlit"]


def test_match_score_hard_rejection_for_missing_required_skill(
    candidate_profile: CandidateProfile,
) -> None:
    """Missing a required skill hard rejects the application."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Frontend Intern",
        location="Malaysia",
        source_text="React internship source text with enough detail.",
        skills=[SkillRequirement(name="React", level=RequirementLevel.REQUIRED)],
    )

    score = calculate_match_score(candidate_profile, vacancy, current_year=2026)

    assert score.score == 0
    assert score.hard_rejected is True
    assert score.missing_required_skills == ["react"]
