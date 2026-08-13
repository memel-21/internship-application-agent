"""Prepare Gmail draft packages with required internship attachments."""

from base64 import urlsafe_b64encode
from mimetypes import guess_type
from pathlib import Path
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError

from internship_agent.domain.email_draft import DraftAttachment, GmailDraftPackage
from internship_agent.domain.vacancy import ApplicationStatus
from internship_agent.exceptions import EmailDraftError
from internship_agent.persistence.models import ApplicationDocumentRecord, ApplicationRecord

EMAIL_ADAPTER = TypeAdapter(EmailStr)
ALLOWED_ATTACHMENT_SUFFIXES = {".pdf", ".docx"}


def prepare_gmail_draft_package(
    *,
    application: ApplicationRecord,
    recipient_email: str,
    cover_letter_path: Path,
    resume_pdf_path: Path,
    academic_transcript_pdf_path: Path,
    university_internship_letter_pdf_path: Path,
) -> GmailDraftPackage:
    """Prepare a validated, unsent Gmail draft package."""

    if application.status != ApplicationStatus.APPROVED.value:
        raise EmailDraftError("Only approved applications can be prepared as Gmail drafts.")
    if not application.application_email_subject or not application.application_email_body:
        raise EmailDraftError("Application email subject and body are required.")

    try:
        recipient = EMAIL_ADAPTER.validate_python(recipient_email)
    except ValidationError as exc:
        raise EmailDraftError("A valid recipient email is required.") from exc
    attachments = [
        _validate_attachment("Cover Letter", cover_letter_path),
        _validate_attachment("Resume (CV)", resume_pdf_path),
        _validate_attachment("Academic Transcript", academic_transcript_pdf_path),
        _validate_attachment("UiTM Internship Letter", university_internship_letter_pdf_path),
    ]
    return GmailDraftPackage(
        to=recipient,
        subject=application.application_email_subject,
        body=application.application_email_body,
        attachments=attachments,
    )


def latest_cover_letter_pdf(
    document_records: list[ApplicationDocumentRecord],
) -> Path | None:
    """Return the newest generated cover letter PDF path when present."""

    pdf_records = [
        record for record in document_records if record.document_type == "cover_letter_pdf"
    ]
    if not pdf_records:
        return None
    return Path(pdf_records[-1].path)


def gmail_mime_payload(package: GmailDraftPackage) -> dict[str, Any]:
    """Build a Gmail connector MIME tree for draft creation."""

    return {
        "mime_type": "multipart/mixed",
        "parts": [
            {
                "mime_type": "text/plain",
                "charset": "UTF-8",
                "body": {"content": package.body},
            },
            *[
                {
                    "mime_type": attachment.mime_type,
                    "filename": attachment.path.name,
                    "content_disposition": "attachment",
                    "body": {
                        "base64_url_content": _base64_url_file(attachment.path),
                    },
                }
                for attachment in package.attachments
            ],
        ],
    }


def _validate_attachment(label: str, path: Path) -> DraftAttachment:
    resolved = path.expanduser().resolve()
    if resolved.suffix.casefold() not in ALLOWED_ATTACHMENT_SUFFIXES:
        raise EmailDraftError(f"{label} must be a PDF or DOCX file.")
    if not resolved.exists():
        raise EmailDraftError(f"{label} attachment is missing: {resolved}")
    if not resolved.is_file():
        raise EmailDraftError(f"{label} attachment is not a file: {resolved}")
    mime_type = guess_type(resolved.name)[0] or "application/octet-stream"
    return DraftAttachment(label=label, path=resolved, mime_type=mime_type)


def _base64_url_file(path: Path) -> str:
    return urlsafe_b64encode(path.read_bytes()).decode("ascii")
