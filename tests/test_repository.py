"""Tests for SQLite application repository."""

from datetime import date
from pathlib import Path

import pytest

from internship_agent.domain.generated_content import (
    GeneratedApplicationContent,
    GeneratedClaim,
)
from internship_agent.domain.review import ReviewDecision
from internship_agent.domain.vacancy import ApplicationStatus, Vacancy
from internship_agent.domain.validation import FindingSeverity, ValidationFinding, ValidationReport
from internship_agent.exceptions import (
    ApprovalBlockedError,
    DuplicateApplicationError,
    InvalidStatusTransitionError,
)
from internship_agent.persistence.repository import ApplicationRepository


def test_application_records_can_be_added_and_retrieved(sqlite_url: str) -> None:
    """Repository stores and retrieves application records."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Intern",
        location="Remote",
        source_text="Python internship source text with enough detail.",
    )

    created = repository.add_application(
        candidate_email="test@example.edu",
        vacancy=vacancy,
        status=ApplicationStatus.DISCOVERED,
        match_score=90.5,
        recommendation="apply",
    )
    retrieved = repository.get_application(created.id)
    audit_logs = repository.list_audit_logs()

    assert retrieved is not None
    assert retrieved.company_name == "Acme"
    assert retrieved.match_score == 90.5
    assert retrieved.recommendation == "apply"
    assert retrieved.vacancy_fingerprint
    assert retrieved.vacancy_source == vacancy.source_text
    assert len(repository.list_applications()) == 1
    assert len(audit_logs) == 2
    assert audit_logs[0].action == "application_created"


def test_duplicate_records_are_detected(sqlite_url: str) -> None:
    """Repository rejects duplicate candidate/company/role records."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Intern",
        location="Remote",
        source_text="Python internship source text with enough detail.",
    )

    repository.add_application(
        candidate_email="test@example.edu",
        vacancy=vacancy,
        status=ApplicationStatus.DISCOVERED,
        match_score=90,
        recommendation="apply",
    )

    with pytest.raises(DuplicateApplicationError):
        repository.add_application(
            candidate_email="test@example.edu",
            vacancy=vacancy,
            status=ApplicationStatus.DISCOVERED,
            match_score=90,
            recommendation="apply",
        )


def test_discovered_application_cannot_transition_directly_to_submitted(
    sqlite_url: str,
) -> None:
    """Repository enforces explicit safe status progression."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Intern",
        location="Remote",
        source_text="Python internship source text with enough detail.",
    )
    created = repository.add_application(
        candidate_email="test@example.edu",
        vacancy=vacancy,
        status=ApplicationStatus.DISCOVERED,
        match_score=90,
        recommendation="apply",
    )

    with pytest.raises(InvalidStatusTransitionError):
        repository.update_status(
            created.id,
            ApplicationStatus.SUBMITTED,
            explicit_submission_confirmation=True,
        )


def test_approved_review_decision_persists_package_and_events(sqlite_url: str) -> None:
    """Repository stores approved packages, validation findings, and review events."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    vacancy = _vacancy()
    report = ValidationReport(
        findings=[
            ValidationFinding(
                severity=FindingSeverity.WARNING,
                code="missing_attachment_reference",
                message="Email body does not mention the resume attachment.",
            )
        ]
    )

    created = repository.record_review_decision(
        candidate_email="test@example.edu",
        vacancy=vacancy,
        content=_content(),
        validation_report=report,
        decision=ReviewDecision.APPROVE,
        match_score=82.5,
        recommendation="apply",
        notes="Reviewed by human.",
    )

    retrieved = repository.get_application(created.id)
    findings = repository.list_validation_findings(created.id)
    approval_events = repository.list_approval_events(created.id)
    audit_logs = repository.list_audit_logs()

    assert retrieved is not None
    assert retrieved.status == ApplicationStatus.APPROVED.value
    assert retrieved.validation_status == "warnings"
    assert retrieved.cover_letter_text == _content().cover_letter
    assert retrieved.application_email_subject == _content().email_subject
    assert retrieved.generated_content_json is not None
    assert findings[0].code == "missing_attachment_reference"
    assert findings[0].severity == FindingSeverity.WARNING.value
    assert approval_events[0].decision == ReviewDecision.APPROVE.value
    assert audit_logs[0].action == "review_decision_recorded"


def test_blocking_findings_prevent_approval(sqlite_url: str) -> None:
    """Blocking validation findings prevent approval persistence."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    report = ValidationReport(
        findings=[
            ValidationFinding(
                severity=FindingSeverity.BLOCKING,
                code="placeholder_present",
                message="Generated content contains a placeholder.",
            )
        ]
    )

    with pytest.raises(ApprovalBlockedError):
        repository.record_review_decision(
            candidate_email="test@example.edu",
            vacancy=_vacancy(),
            content=_content(),
            validation_report=report,
            decision=ReviewDecision.APPROVE,
            match_score=82.5,
            recommendation="apply",
        )

    assert repository.list_applications() == []


def test_rejected_review_decision_allows_blocking_findings(sqlite_url: str) -> None:
    """Rejected packages can be saved with blocking findings for audit history."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    report = ValidationReport(
        findings=[
            ValidationFinding(
                severity=FindingSeverity.BLOCKING,
                code="unsupported_technology",
                message="Generated content mentions unsupported technology.",
            )
        ]
    )

    created = repository.record_review_decision(
        candidate_email="test@example.edu",
        vacancy=_vacancy(),
        content=_content(),
        validation_report=report,
        decision=ReviewDecision.REJECT,
        match_score=0,
        recommendation="skip",
        notes="Rejected due to unsupported claim.",
    )

    retrieved = repository.get_application(created.id)
    findings = repository.list_validation_findings(created.id)
    approval_events = repository.list_approval_events(created.id)

    assert retrieved is not None
    assert retrieved.status == ApplicationStatus.REJECTED.value
    assert retrieved.validation_status == "failed"
    assert retrieved.notes == "Rejected due to unsupported claim."
    assert findings[0].code == "unsupported_technology"
    assert approval_events[0].decision == ReviewDecision.REJECT.value


def test_update_status_records_status_event(sqlite_url: str) -> None:
    """Status updates persist both current status and status history."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    created = repository.record_review_decision(
        candidate_email="test@example.edu",
        vacancy=_vacancy(),
        content=_content(),
        validation_report=ValidationReport(),
        decision=ReviewDecision.APPROVE,
        match_score=82.5,
        recommendation="apply",
    )

    updated = repository.update_status(created.id, ApplicationStatus.READY_TO_SEND)
    status_events = repository.list_status_events(created.id)

    assert updated.status == ApplicationStatus.READY_TO_SEND.value
    assert status_events[-1].from_status == ApplicationStatus.APPROVED.value
    assert status_events[-1].to_status == ApplicationStatus.READY_TO_SEND.value


def test_update_follow_up_date_records_audit_log(sqlite_url: str) -> None:
    """Follow-up date changes are stored and audited."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    created = repository.record_review_decision(
        candidate_email="test@example.edu",
        vacancy=_vacancy(),
        content=_content(),
        validation_report=ValidationReport(),
        decision=ReviewDecision.APPROVE,
        match_score=82.5,
        recommendation="apply",
    )

    updated = repository.update_follow_up_date(created.id, date(2026, 9, 1))
    audit_logs = repository.list_audit_logs()

    assert updated.follow_up_date == date(2026, 9, 1)
    assert audit_logs[-1].action == "follow_up_date_changed"


def test_record_generated_documents_persists_paths(sqlite_url: str, tmp_path: Path) -> None:
    """Generated DOCX and PDF paths are linked to the application."""

    repository = ApplicationRepository(sqlite_url)
    repository.create_schema()
    created = repository.record_review_decision(
        candidate_email="test@example.edu",
        vacancy=_vacancy(),
        content=_content(),
        validation_report=ValidationReport(),
        decision=ReviewDecision.APPROVE,
        match_score=82.5,
        recommendation="apply",
    )
    docx_path = tmp_path / "cover.docx"
    pdf_path = tmp_path / "cover.pdf"

    updated = repository.record_generated_documents(
        created.id,
        docx_path=docx_path,
        pdf_path=pdf_path,
    )
    documents = repository.list_document_records(created.id)

    assert updated.cover_letter_path == str(docx_path)
    assert {document.document_type for document in documents} == {
        "cover_letter_docx",
        "cover_letter_pdf",
    }


def _vacancy() -> Vacancy:
    return Vacancy(
        company_name="Acme",
        role_title="Software Intern",
        location="Remote",
        source_text="Python internship source text with enough detail.",
    )


def _content() -> GeneratedApplicationContent:
    return GeneratedApplicationContent(
        professional_summary="Test Student has verified Python skills.",
        selected_skills=["Python"],
        cover_letter="Dear Acme Team, Test Student is applying for Software Intern.",
        email_subject="Application for Software Intern",
        email_body="Dear Acme Team, my resume is attached.",
        claims=[GeneratedClaim(text="Verified Python skills.", source_refs=["candidate.skills"])],
    )
