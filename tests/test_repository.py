"""Tests for SQLite application repository."""

import pytest

from internship_agent.domain.vacancy import ApplicationStatus, Vacancy
from internship_agent.exceptions import DuplicateApplicationError, InvalidStatusTransitionError
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
