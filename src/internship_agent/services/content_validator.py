"""Deterministic validation for generated application content."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.evidence import EvidenceSelection
from internship_agent.domain.generated_content import GeneratedApplicationContent
from internship_agent.domain.vacancy import Vacancy
from internship_agent.domain.validation import FindingSeverity, ValidationFinding, ValidationReport
from internship_agent.persistence.models import ApplicationRecord


@dataclass(frozen=True)
class AttachmentChecklist:
    """Expected attachment names for deterministic validation."""

    required_references: tuple[str, ...] = ("resume",)


def validate_application_content(
    *,
    candidate: CandidateProfile,
    vacancy: Vacancy,
    content: GeneratedApplicationContent,
    evidence_selection: EvidenceSelection,
    existing_applications: Iterable[ApplicationRecord] = (),
    attachment_checklist: AttachmentChecklist | None = None,
) -> ValidationReport:
    """Validate generated cover letter and email with deterministic checks."""

    full_text = _combined_content(content)
    findings: list[ValidationFinding] = []

    findings.extend(_validate_exact_identity(candidate, vacancy, content, full_text))
    findings.extend(_validate_profile_facts(candidate, full_text))
    findings.extend(_validate_unsupported_terms(full_text, evidence_selection))
    findings.extend(_validate_prohibited_claims(full_text))
    findings.extend(_validate_placeholders(full_text))
    findings.extend(_validate_attachment_references(content, attachment_checklist))
    findings.extend(_validate_email_cover_letter_consistency(content))
    findings.extend(_validate_duplicate_application(vacancy, existing_applications))

    if content.gaps:
        findings.append(
            ValidationFinding(
                severity=FindingSeverity.WARNING,
                code="evidence_gaps_present",
                message="Generated package has evidence gaps that require manual review.",
            )
        )

    return ValidationReport(findings=findings)


def _validate_exact_identity(
    candidate: CandidateProfile,
    vacancy: Vacancy,
    content: GeneratedApplicationContent,
    full_text: str,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if vacancy.company_name not in full_text:
        findings.append(
            _blocking(
                "missing_company_name",
                "Generated content is missing the exact company name.",
            )
        )
    if vacancy.role_title not in full_text:
        findings.append(
            _blocking(
                "missing_role_title",
                "Generated content is missing the exact role title.",
            )
        )
    if candidate.full_name not in full_text:
        findings.append(
            _blocking(
                "missing_candidate_name",
                "Generated content is missing the candidate name.",
            )
        )

    subject = content.email_subject.casefold()
    if vacancy.role_title.casefold() not in subject:
        findings.append(
            _blocking(
                "email_subject_role_mismatch",
                "Email subject does not include the exact role title.",
            )
        )
    return findings


def _validate_profile_facts(candidate: CandidateProfile, full_text: str) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    start_date = candidate.internship.start_date.isoformat()
    end_date = candidate.internship.end_date.isoformat()
    date_like_values = set(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", full_text))
    allowed_dates = {start_date, end_date}
    incorrect_dates = sorted(date_like_values - allowed_dates)
    if incorrect_dates:
        findings.append(
            _blocking(
                "incorrect_internship_dates",
                "Generated content contains dates not in the verified profile: "
                f"{', '.join(incorrect_dates)}.",
            )
        )

    cgpa_pattern = re.compile(r"\b[0-4]\.\d{1,2}\s*(?:/|out of)\s*4(?:\.0{1,2})?\b", re.IGNORECASE)
    expected_cgpa = f"{candidate.education.cgpa:.2f}"
    for match in cgpa_pattern.findall(full_text):
        if expected_cgpa not in match:
            findings.append(
                _blocking(
                    "cgpa_mismatch",
                    "Generated content contains a CGPA that differs from the profile.",
                )
            )
            break
    return findings


def _validate_unsupported_terms(
    full_text: str,
    evidence_selection: EvidenceSelection,
) -> list[ValidationFinding]:
    allowed_text = " ".join(item.text for item in evidence_selection.selected).casefold()
    findings: list[ValidationFinding] = []
    monitored_terms = ("aws", "azure", "gcp", "docker", "kubernetes", "react", "node.js")
    for term in monitored_terms:
        if term in full_text.casefold() and term not in allowed_text:
            findings.append(
                _blocking(
                    "unsupported_technology",
                    f"Generated content mentions unsupported technology: {term}.",
                )
            )
    return findings


def _validate_prohibited_claims(full_text: str) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    blocking_patterns = {
        "professional_experience": r"\b(professional|paid)\s+.*\b(experience|employment)\b",
        "production_deployment": r"\b(production deployment|deployed (?:to|in) production)\b",
        "medical_diagnostic": (
            r"\b(diagnos(?:e|is|tic)|clinically validated|hospital implementation)\b"
        ),
        "expert_claim": (
            r"\bexpert\b|\bextensive professional experience\b|"
            r"\bproven production deployment\b"
        ),
    }
    for code, pattern in blocking_patterns.items():
        if re.search(pattern, full_text, re.IGNORECASE):
            findings.append(
                _blocking(code, f"Generated content contains prohibited claim: {code}.")
            )
    return findings


def _validate_placeholders(full_text: str) -> list[ValidationFinding]:
    placeholder_patterns = (r"\bTBD\b", r"\bTODO\b", r"\[.+?\]", r"\{\{.+?\}\}", r"<.+?>")
    if any(re.search(pattern, full_text, re.IGNORECASE) for pattern in placeholder_patterns):
        return [
            _blocking(
                "placeholder_present",
                "Generated content contains an empty placeholder.",
            )
        ]
    return []


def _validate_attachment_references(
    content: GeneratedApplicationContent,
    attachment_checklist: AttachmentChecklist | None,
) -> list[ValidationFinding]:
    checklist = attachment_checklist or AttachmentChecklist()
    email_text = content.email_body.casefold()
    findings: list[ValidationFinding] = []
    for required_reference in checklist.required_references:
        if required_reference not in email_text and "attach" not in email_text:
            findings.append(
                ValidationFinding(
                    severity=FindingSeverity.WARNING,
                    code="missing_attachment_reference",
                    message=(
                        "Email body does not mention expected attachment reference: "
                        f"{required_reference}."
                    ),
                )
            )
    return findings


def _validate_email_cover_letter_consistency(
    content: GeneratedApplicationContent,
) -> list[ValidationFinding]:
    email_text = content.email_body.casefold()
    cover_text = content.cover_letter.casefold()
    findings: list[ValidationFinding] = []
    company_like_values = _company_like_values(content.cover_letter)
    for value in company_like_values:
        if value.casefold() not in email_text:
            findings.append(
                ValidationFinding(
                    severity=FindingSeverity.WARNING,
                    code="email_cover_letter_mismatch",
                    message="Email and cover letter appear to reference different organisations.",
                )
            )
            break
    if "intern" in cover_text and "intern" not in email_text:
        findings.append(
            ValidationFinding(
                severity=FindingSeverity.WARNING,
                code="email_role_mismatch",
                message="Email and cover letter may describe different roles.",
            )
        )
    return findings


def _validate_duplicate_application(
    vacancy: Vacancy,
    existing_applications: Iterable[ApplicationRecord],
) -> list[ValidationFinding]:
    for application in existing_applications:
        if (
            application.company_name.casefold() == vacancy.company_name.casefold()
            and application.role_title.casefold() == vacancy.role_title.casefold()
        ):
            return [
                _blocking(
                    "duplicate_application",
                    "An application for this company and role already exists.",
                )
            ]
    return []


def _combined_content(content: GeneratedApplicationContent) -> str:
    return "\n".join(
        [
            content.professional_summary,
            " ".join(content.selected_skills),
            content.cover_letter,
            content.email_subject,
            content.email_body,
        ]
    )


def _company_like_values(text: str) -> list[str]:
    return re.findall(r"\b[A-Z][A-Za-z0-9& ]{2,40}\s(?:Sdn Bhd|Berhad|Ltd|Inc|Team)\b", text)


def _blocking(code: str, message: str) -> ValidationFinding:
    return ValidationFinding(severity=FindingSeverity.BLOCKING, code=code, message=message)
