"""Tests for approved cover letter document generation."""

from pathlib import Path

import pytest
from docx import Document

from internship_agent.domain.vacancy import ApplicationStatus
from internship_agent.exceptions import DocumentGenerationError
from internship_agent.persistence.models import ApplicationRecord
from internship_agent.services.document_generator import generate_cover_letter_documents


def test_generate_cover_letter_documents_creates_docx_and_pdf(tmp_path: Path) -> None:
    """Approved applications can be exported to DOCX and PDF."""

    application = _application()

    paths = generate_cover_letter_documents(application, output_dir=tmp_path)

    assert paths.docx_path.exists()
    assert paths.pdf_path.exists()
    assert paths.pdf_path.read_bytes().startswith(b"%PDF")
    document = Document(paths.docx_path)
    paragraph_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Cover Letter" in paragraph_text
    assert "Acme" in paragraph_text
    assert application.cover_letter_text in paragraph_text


def test_generate_cover_letter_documents_refuses_overwrite(tmp_path: Path) -> None:
    """Existing documents are not overwritten without an explicit flag."""

    application = _application()
    generate_cover_letter_documents(application, output_dir=tmp_path)

    with pytest.raises(DocumentGenerationError, match="Refusing to overwrite"):
        generate_cover_letter_documents(application, output_dir=tmp_path)


def test_generate_cover_letter_documents_requires_approval(tmp_path: Path) -> None:
    """Rejected or unreviewed applications cannot generate cover letters."""

    application = _application(status=ApplicationStatus.REJECTED.value)

    with pytest.raises(DocumentGenerationError, match="Only approved"):
        generate_cover_letter_documents(application, output_dir=tmp_path)


def _application(status: str = ApplicationStatus.APPROVED.value) -> ApplicationRecord:
    return ApplicationRecord(
        id=7,
        candidate_email="test@example.edu",
        company_name="Acme",
        role_title="Software Intern",
        vacancy_fingerprint="abc",
        vacancy_source="Python internship source text with enough detail.",
        match_score=82.5,
        recommendation="apply",
        status=status,
        validation_status="passed",
        cover_letter_text=(
            "Dear Acme Team,\n\n"
            "Test Student is applying for Software Intern.\n\n"
            "Sincerely,\nTest Student"
        ),
        notes="",
    )
