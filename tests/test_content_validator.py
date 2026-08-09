"""Tests for deterministic generated-content validation."""

from datetime import datetime

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.evidence import EvidenceItem, EvidenceSelection
from internship_agent.domain.generated_content import (
    GeneratedApplicationContent,
    GeneratedClaim,
)
from internship_agent.domain.vacancy import Vacancy
from internship_agent.domain.validation import FindingSeverity, ValidationReport
from internship_agent.persistence.models import ApplicationRecord
from internship_agent.services.content_validator import validate_application_content


def _content(
    candidate: CandidateProfile,
    vacancy: Vacancy,
    *,
    cover_letter: str | None = None,
    email_body: str | None = None,
    email_subject: str | None = None,
    professional_summary: str | None = None,
) -> GeneratedApplicationContent:
    base_cover = (
        f"Dear {vacancy.company_name} Hiring Team,\n\n"
        f"I am applying for the {vacancy.role_title} position at {vacancy.company_name}. "
        f"{candidate.full_name} has verified Python skills. "
        f"My internship dates are {candidate.internship.start_date.isoformat()} to "
        f"{candidate.internship.end_date.isoformat()}.\n\n"
        f"Sincerely,\n{candidate.full_name}"
    )
    base_email = (
        f"Dear {vacancy.company_name} Hiring Team,\n\n"
        f"I am applying for the {vacancy.role_title}. "
        f"My resume is attached.\n\nRegards,\n{candidate.full_name}"
    )
    return GeneratedApplicationContent(
        professional_summary=professional_summary
        or f"{candidate.full_name} has verified Python skills.",
        selected_skills=["Python"],
        cover_letter=cover_letter or base_cover,
        email_subject=email_subject or f"Application for {vacancy.role_title}",
        email_body=email_body or base_email,
        claims=[GeneratedClaim(text="Verified Python skills.", source_refs=["candidate.skills"])],
    )


def _selection() -> EvidenceSelection:
    return EvidenceSelection(
        selected=[
            EvidenceItem(
                evidence_id="candidate.skills",
                title="Skills",
                text="Python, SQL, Streamlit",
                source_ref="candidate.skills",
                keywords=["Python", "SQL", "Streamlit"],
            )
        ]
    )


def _vacancy() -> Vacancy:
    return Vacancy(
        company_name="Acme",
        role_title="Software Engineering Intern",
        source_text="Python internship source text with enough detail.",
    )


def _blocking_codes(report_codes: list[tuple[FindingSeverity, str]]) -> set[str]:
    return {code for severity, code in report_codes if severity == FindingSeverity.BLOCKING}


def _codes(report: ValidationReport) -> list[tuple[FindingSeverity, str]]:
    return [(finding.severity, finding.code) for finding in report.findings]


def test_validator_blocks_missing_exact_company_name(candidate_profile: CandidateProfile) -> None:
    """Exact company name must appear in generated content."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear Hiring Team, I am applying for Software Engineering Intern. Test Student"
        ),
        email_body="Dear Hiring Team, My resume is attached. Regards, Test Student",
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "missing_company_name" in _blocking_codes(_codes(report))


def test_validator_blocks_missing_exact_role_title(candidate_profile: CandidateProfile) -> None:
    """Exact role title must appear in generated content."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        email_subject="Application",
        cover_letter=f"Dear Acme Team, {candidate_profile.full_name} is applying.",
        email_body=f"Dear Acme Team, My resume is attached. Regards, {candidate_profile.full_name}",
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "missing_role_title" in _blocking_codes(_codes(report))


def test_validator_blocks_missing_candidate_name(candidate_profile: CandidateProfile) -> None:
    """Candidate name must appear in generated content."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter="Dear Acme Team, I am applying for Software Engineering Intern.",
        email_body="Dear Acme Team, My resume is attached.",
        professional_summary="Verified Python skills.",
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "missing_candidate_name" in _blocking_codes(_codes(report))


def test_validator_blocks_incorrect_dates(candidate_profile: CandidateProfile) -> None:
    """Internship dates must match the verified profile."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear Acme Hiring Team, I am applying for Software Engineering Intern. "
            "Test Student is available from 2026-01-01 to 2026-12-26."
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "incorrect_internship_dates" in _blocking_codes(_codes(report))


def test_validator_blocks_cgpa_mismatch(candidate_profile: CandidateProfile) -> None:
    """CGPA must remain consistent with the verified profile."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear Acme Hiring Team, I am applying for Software Engineering Intern. "
            "Test Student has a CGPA of 4.00 out of 4.00."
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "cgpa_mismatch" in _blocking_codes(_codes(report))


def test_validator_blocks_unsupported_technology(candidate_profile: CandidateProfile) -> None:
    """Unsupported technologies cannot be introduced as claims."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear Acme Hiring Team, I am applying for Software Engineering Intern. "
            "Test Student has verified AWS deployment experience."
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "unsupported_technology" in _blocking_codes(_codes(report))


def test_validator_blocks_prohibited_employment_claim(candidate_profile: CandidateProfile) -> None:
    """Unsupported professional employment claims are blocking."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear Acme Hiring Team, I am applying for Software Engineering Intern. "
            "Test Student has paid machine-learning employment experience."
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "professional_experience" in _blocking_codes(_codes(report))


def test_validator_blocks_medical_diagnostic_claim(candidate_profile: CandidateProfile) -> None:
    """Medical diagnostic capability claims are prohibited."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear Acme Hiring Team, I am applying for Software Engineering Intern. "
            "Test Student built a medical diagnostic tool."
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "medical_diagnostic" in _blocking_codes(_codes(report))


def test_validator_blocks_placeholders(candidate_profile: CandidateProfile) -> None:
    """Empty placeholders are blocking."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        cover_letter=(
            "Dear [Company], Test Student applies for Software Engineering Intern at Acme."
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert "placeholder_present" in _blocking_codes(_codes(report))


def test_validator_blocks_duplicate_application(candidate_profile: CandidateProfile) -> None:
    """Duplicate applications are blocking findings."""

    vacancy = _vacancy()
    existing = ApplicationRecord(
        candidate_email="test@example.edu",
        company_name="Acme",
        role_title="Software Engineering Intern",
        vacancy_fingerprint="abc",
        vacancy_source="source",
        match_score=80,
        recommendation="apply",
        status="discovered",
        validation_status="not_validated",
        notes="",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=_content(candidate_profile, vacancy),
        evidence_selection=_selection(),
        existing_applications=[existing],
    )

    assert "duplicate_application" in _blocking_codes(_codes(report))


def test_validator_warns_missing_attachment_reference(candidate_profile: CandidateProfile) -> None:
    """Missing attachment reference is visible but not blocking."""

    vacancy = _vacancy()
    content = _content(
        candidate_profile,
        vacancy,
        email_body=(
            "Dear Acme Team, I am applying for Software Engineering Intern. Regards, Test Student"
        ),
    )

    report = validate_application_content(
        candidate=candidate_profile,
        vacancy=vacancy,
        content=content,
        evidence_selection=_selection(),
    )

    assert (FindingSeverity.WARNING, "missing_attachment_reference") in _codes(report)
