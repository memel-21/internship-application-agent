"""Tests for Gmail draft package preparation."""

from pathlib import Path

import pytest

from internship_agent.domain.vacancy import ApplicationStatus
from internship_agent.exceptions import EmailDraftError
from internship_agent.persistence.models import ApplicationDocumentRecord, ApplicationRecord
from internship_agent.services.email_draft import (
    gmail_mime_payload,
    latest_cover_letter_pdf,
    prepare_gmail_draft_package,
)


def test_prepare_gmail_draft_package_requires_all_attachments(tmp_path: Path) -> None:
    """A draft package includes the generated cover letter and official documents."""

    cover = _write_file(tmp_path / "cover.pdf")
    resume = _write_file(tmp_path / "resume.pdf")
    transcript = _write_file(tmp_path / "transcript.pdf")
    letter = _write_file(tmp_path / "letter.pdf")

    package = prepare_gmail_draft_package(
        application=_application(),
        recipient_email="hr@example.com",
        cover_letter_path=cover,
        resume_pdf_path=resume,
        academic_transcript_pdf_path=transcript,
        university_internship_letter_pdf_path=letter,
    )

    assert package.to == "hr@example.com"
    assert package.subject == "Application for Software Intern"
    assert [attachment.label for attachment in package.attachments] == [
        "Cover Letter",
        "Resume (CV)",
        "Academic Transcript",
        "UiTM Internship Letter",
    ]


def test_prepare_gmail_draft_package_blocks_missing_attachment(tmp_path: Path) -> None:
    """Missing required files block draft preparation."""

    existing = _write_file(tmp_path / "cover.pdf")

    with pytest.raises(EmailDraftError, match="Resume"):
        prepare_gmail_draft_package(
            application=_application(),
            recipient_email="hr@example.com",
            cover_letter_path=existing,
            resume_pdf_path=tmp_path / "missing.pdf",
            academic_transcript_pdf_path=existing,
            university_internship_letter_pdf_path=existing,
        )


def test_prepare_gmail_draft_package_requires_approved_application(tmp_path: Path) -> None:
    """Only approved applications can be prepared for Gmail drafts."""

    existing = _write_file(tmp_path / "cover.pdf")

    with pytest.raises(EmailDraftError, match="Only approved"):
        prepare_gmail_draft_package(
            application=_application(status=ApplicationStatus.REJECTED.value),
            recipient_email="hr@example.com",
            cover_letter_path=existing,
            resume_pdf_path=existing,
            academic_transcript_pdf_path=existing,
            university_internship_letter_pdf_path=existing,
        )


def test_gmail_mime_payload_contains_all_attachments(tmp_path: Path) -> None:
    """Prepared packages can be converted to a Gmail connector MIME tree."""

    existing = _write_file(tmp_path / "cover.pdf", content=b"pdf-bytes")
    package = prepare_gmail_draft_package(
        application=_application(),
        recipient_email="hr@example.com",
        cover_letter_path=existing,
        resume_pdf_path=existing,
        academic_transcript_pdf_path=existing,
        university_internship_letter_pdf_path=existing,
    )

    payload = gmail_mime_payload(package)

    assert payload["mime_type"] == "multipart/mixed"
    assert len(payload["parts"]) == 5
    assert payload["parts"][1]["filename"] == "cover.pdf"
    assert payload["parts"][1]["body"]["base64_url_content"]


def test_latest_cover_letter_pdf_returns_newest_pdf_record() -> None:
    """The latest generated cover letter PDF is selected from document records."""

    records = [
        ApplicationDocumentRecord(
            application_id=1,
            document_type="cover_letter_docx",
            path="cover.docx",
        ),
        ApplicationDocumentRecord(
            application_id=1,
            document_type="cover_letter_pdf",
            path="first.pdf",
        ),
        ApplicationDocumentRecord(
            application_id=1,
            document_type="cover_letter_pdf",
            path="latest.pdf",
        ),
    ]

    assert latest_cover_letter_pdf(records) == Path("latest.pdf")


def _write_file(path: Path, *, content: bytes = b"content") -> Path:
    path.write_bytes(content)
    return path


def _application(status: str = ApplicationStatus.APPROVED.value) -> ApplicationRecord:
    return ApplicationRecord(
        id=1,
        candidate_email="test@example.edu",
        company_name="Acme",
        role_title="Software Intern",
        vacancy_fingerprint="abc",
        vacancy_source="Python internship source text with enough detail.",
        match_score=82.5,
        recommendation="apply",
        status=status,
        validation_status="passed",
        application_email_subject="Application for Software Intern",
        application_email_body="Dear Acme Team,\n\nPlease find my documents attached.",
        notes="",
    )
