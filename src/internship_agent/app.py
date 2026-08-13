"""Minimal Streamlit interface for local vacancy analysis."""

from datetime import date
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from internship_agent.domain.evidence import EvidenceSelection
from internship_agent.domain.generated_content import GeneratedApplicationContent
from internship_agent.domain.review import ReviewDecision
from internship_agent.domain.vacancy import (
    ApplicationStatus,
    RequirementLevel,
    SkillRequirement,
    Vacancy,
)
from internship_agent.domain.validation import FindingSeverity, ValidationReport
from internship_agent.exceptions import (
    ApprovalBlockedError,
    CandidateProfileError,
    ContentGenerationError,
    DocumentGenerationError,
    DuplicateApplicationError,
    EmailDraftError,
    EvidenceError,
    InternshipAgentError,
    InvalidStatusTransitionError,
    RepositoryError,
    VacancyExtractionError,
)
from internship_agent.persistence.models import ApplicationDocumentRecord, ApplicationRecord
from internship_agent.persistence.repository import ApplicationRepository
from internship_agent.services.content_generator import create_content_generator
from internship_agent.services.content_validator import validate_application_content
from internship_agent.services.document_generator import generate_cover_letter_documents
from internship_agent.services.email_draft import (
    latest_cover_letter_pdf,
    prepare_gmail_draft_package,
)
from internship_agent.services.evidence_loader import load_approved_evidence
from internship_agent.services.evidence_selector import select_evidence
from internship_agent.services.profile_loader import load_candidate_profile
from internship_agent.services.scoring import calculate_match_score
from internship_agent.services.vacancy_extractor import create_vacancy_extractor
from internship_agent.settings import Settings


def render_app(settings: Settings) -> None:
    """Render the Milestone 1 Streamlit application."""

    st.set_page_config(page_title="Internship Application Agent", layout="wide")
    st.title("Internship Application Agent")

    st.caption("Final MVP: prepare, validate, approve, export, and track applications locally.")

    profile_path_text = st.text_input(
        "Candidate profile JSON path",
        value=str(settings.candidate_profile_path),
    )
    profile_path = Path(profile_path_text)

    try:
        candidate = load_candidate_profile(profile_path)
    except CandidateProfileError as exc:
        st.error(str(exc))
        candidate = None

    if candidate is not None:
        st.success(f"Loaded verified profile for {candidate.full_name}")
        st.write(
            {
                "email": candidate.email,
                "university": candidate.university,
                "degree": candidate.degree,
                "graduation_year": candidate.graduation_year,
                "skills": candidate.flattened_skills(),
            }
        )

    vacancy_text = st.text_area("Paste vacancy text", height=240)
    if st.button("Analyse vacancy"):
        try:
            extractor = create_vacancy_extractor(
                demo_mode=settings.demo_mode,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
            vacancy = extractor.extract(vacancy_text)
        except VacancyExtractionError as exc:
            st.error(str(exc))
        else:
            st.success("Vacancy extracted and validated.")
            if vacancy.extraction_warnings:
                st.warning("Manual review needed for extraction warnings.")
                st.write(vacancy.extraction_warnings)
            st.json(vacancy.model_dump(mode="json"))
            st.session_state["vacancy"] = vacancy.model_dump(mode="json")

    with st.expander("Create a manual vacancy object for local testing"):
        company_name = st.text_input("Company name", value="Example Company")
        role_title = st.text_input("Role title", value="Software Engineering Intern")
        location = st.text_input("Location", value="Kuala Lumpur, Malaysia")
        required_skills = st.text_input("Required skills, comma-separated", value="Python, SQL")
        preferred_skills = st.text_input("Preferred skills, comma-separated", value="Streamlit")

        if st.button("Validate manual vacancy"):
            try:
                vacancy = Vacancy(
                    company_name=company_name,
                    role_title=role_title,
                    location=location,
                    skills=[
                        *[
                            SkillRequirement(name=skill, level=RequirementLevel.REQUIRED)
                            for skill in _split_csv(required_skills)
                        ],
                        *[
                            SkillRequirement(name=skill, level=RequirementLevel.PREFERRED)
                            for skill in _split_csv(preferred_skills)
                        ],
                    ],
                    eligibility_requirements=["Must be a current student"],
                    deadline=date.today().replace(year=date.today().year + 1),
                    source_text=(
                        vacancy_text or "Manual vacancy text placeholder for local testing."
                    ),
                )
            except ValidationError as exc:
                st.error(f"Vacancy validation failed: {exc.errors()[0]['msg']}")
            else:
                st.success("Manual vacancy object is valid.")
                st.json(vacancy.model_dump(mode="json"))
                st.session_state["vacancy"] = vacancy.model_dump(mode="json")

    if candidate is not None and "vacancy" in st.session_state:
        st.divider()
        st.subheader("Prepare grounded application draft")
        vacancy = Vacancy.model_validate(st.session_state["vacancy"])
        if st.button("Generate grounded draft"):
            try:
                evidence_items = load_approved_evidence(candidate, base_path=Path.cwd())
                evidence_selection = select_evidence(candidate, vacancy, evidence_items)
                generator = create_content_generator(
                    demo_mode=settings.demo_mode,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
                content = generator.generate(
                    candidate=candidate,
                    vacancy=vacancy,
                    evidence_selection=evidence_selection,
                )
            except (ContentGenerationError, EvidenceError) as exc:
                st.error(str(exc))
            else:
                st.session_state["evidence_selection"] = evidence_selection.model_dump(mode="json")
                st.session_state["generated_content"] = content.model_dump(mode="json")

        if "evidence_selection" in st.session_state:
            st.write("Selected evidence")
            st.json(st.session_state["evidence_selection"])

        if "generated_content" in st.session_state:
            generated = st.session_state["generated_content"]
            evidence_selection = EvidenceSelection.model_validate(
                st.session_state["evidence_selection"]
            )
            content = GeneratedApplicationContent.model_validate(generated)
            validation_report = validate_application_content(
                candidate=candidate,
                vacancy=vacancy,
                content=content,
                evidence_selection=evidence_selection,
            )
            st.text_area(
                "Professional summary",
                value=generated["professional_summary"],
                height=100,
            )
            st.text_input("Email subject", value=generated["email_subject"])
            st.text_area("Email body", value=generated["email_body"], height=180)
            st.text_area("Cover letter", value=generated["cover_letter"], height=360)
            if generated["gaps"]:
                st.warning("Evidence gaps")
                st.write(generated["gaps"])
            if generated["warnings"]:
                st.warning("Generation warnings")
                st.write(generated["warnings"])
            st.subheader("Validation findings")
            if validation_report.findings:
                for finding in validation_report.findings:
                    message = f"{finding.code}: {finding.message}"
                    if finding.severity == FindingSeverity.BLOCKING:
                        st.error(message)
                    elif finding.severity == FindingSeverity.WARNING:
                        st.warning(message)
                    else:
                        st.info(message)
            else:
                st.success("No validation findings.")
            if validation_report.has_blocking_findings:
                st.error("Blocking findings must be resolved before approval.")
            st.subheader("Human review decision")
            review_notes = st.text_area("Review notes", height=100)
            match_score = calculate_match_score(candidate, vacancy, current_year=date.today().year)
            st.write(
                {
                    "match_score": match_score.score,
                    "recommendation": match_score.recommendation.value,
                }
            )
            candidate_email = candidate.email
            if candidate_email is None:
                st.error("Candidate email is missing, so the package cannot be saved.")
            approve_column, reject_column = st.columns(2)
            with approve_column:
                if st.button(
                    "Approve package",
                    disabled=validation_report.has_blocking_findings or candidate_email is None,
                ):
                    if candidate_email is None:
                        st.error("Candidate email is required before saving a review decision.")
                        return
                    _save_review_decision(
                        settings=settings,
                        candidate_email=candidate_email,
                        vacancy=vacancy,
                        content=content,
                        validation_report=validation_report,
                        decision=ReviewDecision.APPROVE,
                        match_score=match_score.score,
                        recommendation=match_score.recommendation.value,
                        notes=review_notes,
                    )
            with reject_column:
                if st.button("Reject package", disabled=candidate_email is None):
                    if candidate_email is None:
                        st.error("Candidate email is required before saving a review decision.")
                        return
                    _save_review_decision(
                        settings=settings,
                        candidate_email=candidate_email,
                        vacancy=vacancy,
                        content=content,
                        validation_report=validation_report,
                        decision=ReviewDecision.REJECT,
                        match_score=match_score.score,
                        recommendation=match_score.recommendation.value,
                        notes=review_notes,
                    )

    st.divider()
    _render_tracking_dashboard(settings)

    if settings.demo_mode:
        st.info("Demo mode is enabled, so vacancy extraction uses deterministic local logic.")
    else:
        st.info("Demo mode is disabled. Vacancy extraction uses the OpenAI Responses API.")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _render_tracking_dashboard(settings: Settings) -> None:
    st.subheader("Application tracker")
    repository = ApplicationRepository(settings.database_url)
    try:
        repository.create_schema()
        applications = repository.list_applications()
    except RepositoryError as exc:
        st.error(str(exc))
        return

    if not applications:
        st.info("No saved applications yet.")
        return

    with st.container(horizontal=True):
        st.metric("Total", len(applications), border=True)
        st.metric(
            "Approved",
            sum(
                application.status == ApplicationStatus.APPROVED.value
                for application in applications
            ),
            border=True,
        )
        st.metric(
            "Submitted",
            sum(
                application.status == ApplicationStatus.SUBMITTED.value
                for application in applications
            ),
            border=True,
        )
        st.metric(
            "Need follow-up",
            sum(application.follow_up_date is not None for application in applications),
            border=True,
        )

    st.dataframe(
        _application_rows(applications),
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", format="%d"),
            "company": st.column_config.TextColumn("Company", pinned=True),
            "role": st.column_config.TextColumn("Role"),
            "score": st.column_config.NumberColumn("Score", format="%.1f"),
            "follow_up": st.column_config.DateColumn("Follow-up"),
        },
    )

    application_options = {
        f"#{application.id} - {application.company_name} - {application.role_title}": application.id
        for application in applications
    }
    selected_label = st.selectbox("Review saved application", list(application_options))
    selected = repository.get_application(application_options[selected_label])
    if selected is None:
        st.error("Selected application no longer exists.")
        return

    with st.container(border=True):
        st.write(
            {
                "status": selected.status,
                "validation_status": selected.validation_status,
                "recommendation": selected.recommendation,
                "match_score": selected.match_score,
                "follow_up_date": selected.follow_up_date,
                "cover_letter_path": selected.cover_letter_path,
            }
        )
        if selected.application_email_subject:
            st.text_input(
                "Saved email subject",
                value=selected.application_email_subject,
                disabled=True,
                key=f"subject_{selected.id}",
            )
        if selected.application_email_body:
            st.text_area(
                "Saved email body",
                value=selected.application_email_body,
                disabled=True,
                height=140,
                key=f"email_{selected.id}",
            )
        if selected.cover_letter_text:
            st.text_area(
                "Saved cover letter",
                value=selected.cover_letter_text,
                disabled=True,
                height=260,
                key=f"cover_{selected.id}",
            )

    _render_document_actions(settings, repository, selected)
    _render_status_actions(repository, selected)
    _render_application_history(repository, selected)


def _application_rows(applications: list[ApplicationRecord]) -> list[dict[str, object]]:
    return [
        {
            "id": application.id,
            "company": application.company_name,
            "role": application.role_title,
            "status": application.status,
            "score": application.match_score,
            "validation": application.validation_status,
            "follow_up": application.follow_up_date,
        }
        for application in applications
    ]


def _render_document_actions(
    settings: Settings,
    repository: ApplicationRepository,
    application: ApplicationRecord,
) -> None:
    st.subheader("Documents")
    documents = repository.list_document_records(application.id)
    if documents:
        st.write(
            [
                {
                    "type": document.document_type,
                    "path": document.path,
                    "created_at": document.created_at,
                }
                for document in documents
            ]
        )
    if application.status != ApplicationStatus.APPROVED.value:
        st.info("DOCX and PDF generation is available only for approved applications.")
        return

    overwrite = st.checkbox(
        "Overwrite existing generated files",
        value=False,
        key=f"overwrite_docs_{application.id}",
    )
    if st.button("Generate DOCX and PDF", key=f"generate_docs_{application.id}"):
        try:
            paths = generate_cover_letter_documents(
                application,
                output_dir=settings.output_dir,
                overwrite=overwrite,
            )
            repository.record_generated_documents(
                application.id,
                docx_path=paths.docx_path,
                pdf_path=paths.pdf_path,
            )
        except (DocumentGenerationError, RepositoryError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Generated {paths.docx_path.name} and {paths.pdf_path.name}.")
            st.rerun()

    _render_email_draft_actions(settings, repository, application, documents)


def _render_email_draft_actions(
    settings: Settings,
    repository: ApplicationRepository,
    application: ApplicationRecord,
    documents: list[ApplicationDocumentRecord],
) -> None:
    st.subheader("Gmail draft package")
    if application.status != ApplicationStatus.APPROVED.value:
        st.info("Gmail draft preparation is available only for approved applications.")
        return

    cover_letter_pdf = latest_cover_letter_pdf(documents)
    recipient = st.text_input(
        "Recipient email",
        value=application.application_recipient_email or "",
        key=f"draft_recipient_{application.id}",
    )
    cover_path = st.text_input(
        "Generated cover letter PDF",
        value=str(cover_letter_pdf or ""),
        key=f"draft_cover_{application.id}",
    )
    resume_path = st.text_input(
        "Resume PDF",
        value=str(settings.resume_pdf_path or ""),
        key=f"draft_resume_{application.id}",
    )
    transcript_path = st.text_input(
        "Academic transcript PDF",
        value=str(settings.academic_transcript_pdf_path or ""),
        key=f"draft_transcript_{application.id}",
    )
    internship_letter_path = st.text_input(
        "UiTM internship letter PDF",
        value=str(settings.university_internship_letter_pdf_path or ""),
        key=f"draft_internship_letter_{application.id}",
    )

    if application.gmail_draft_url:
        st.success(f"Gmail draft recorded: {application.gmail_draft_url}")
    elif application.gmail_draft_id:
        st.success(f"Gmail draft recorded: {application.gmail_draft_id}")

    if st.button("Validate draft package", key=f"validate_draft_{application.id}"):
        try:
            package = prepare_gmail_draft_package(
                application=application,
                recipient_email=recipient,
                cover_letter_path=Path(cover_path),
                resume_pdf_path=Path(resume_path),
                academic_transcript_pdf_path=Path(transcript_path),
                university_internship_letter_pdf_path=Path(internship_letter_path),
            )
        except EmailDraftError as exc:
            st.error(str(exc))
        else:
            st.success("Draft package is ready for Gmail draft creation.")
            st.write(
                [
                    {
                        "attachment": attachment.label,
                        "file": attachment.path.name,
                        "mime_type": attachment.mime_type,
                    }
                    for attachment in package.attachments
                ]
            )

    with st.expander("Record Gmail draft after creation"):
        draft_id = st.text_input("Gmail draft ID", key=f"gmail_draft_id_{application.id}")
        draft_url = st.text_input("Gmail draft URL", key=f"gmail_draft_url_{application.id}")
        if st.button("Mark Gmail draft created", key=f"mark_draft_{application.id}"):
            if not draft_id.strip():
                st.error("Gmail draft ID is required.")
                return
            try:
                repository.record_gmail_draft(
                    application.id,
                    recipient_email=recipient,
                    draft_id=draft_id.strip(),
                    draft_url=draft_url.strip() or None,
                )
            except RepositoryError as exc:
                st.error(str(exc))
            else:
                st.success("Gmail draft metadata saved.")
                st.rerun()


def _render_status_actions(
    repository: ApplicationRepository,
    application: ApplicationRecord,
) -> None:
    st.subheader("Status and follow-up")
    status_values = [status.value for status in ApplicationStatus]
    selected_status = st.selectbox(
        "Status",
        status_values,
        index=status_values.index(application.status),
        key=f"status_{application.id}",
    )
    explicit_submission_confirmation = False
    if selected_status == ApplicationStatus.SUBMITTED.value:
        explicit_submission_confirmation = st.checkbox(
            "I explicitly confirm this application was submitted manually.",
            key=f"submitted_confirm_{application.id}",
        )
    if st.button("Update status", key=f"update_status_{application.id}"):
        try:
            repository.update_status(
                application.id,
                ApplicationStatus(selected_status),
                explicit_submission_confirmation=explicit_submission_confirmation,
            )
        except (InvalidStatusTransitionError, RepositoryError) as exc:
            st.error(str(exc))
        else:
            st.success("Status updated.")
            st.rerun()

    follow_up_value = st.date_input(
        "Follow-up date",
        value=application.follow_up_date or date.today(),
        key=f"follow_up_{application.id}",
    )
    with st.container(horizontal=True):
        if st.button("Save follow-up date", key=f"save_follow_up_{application.id}"):
            try:
                repository.update_follow_up_date(application.id, follow_up_value)
            except RepositoryError as exc:
                st.error(str(exc))
            else:
                st.success("Follow-up date saved.")
                st.rerun()
        if st.button("Clear follow-up date", key=f"clear_follow_up_{application.id}"):
            try:
                repository.update_follow_up_date(application.id, None)
            except RepositoryError as exc:
                st.error(str(exc))
            else:
                st.success("Follow-up date cleared.")
                st.rerun()


def _render_application_history(
    repository: ApplicationRepository,
    application: ApplicationRecord,
) -> None:
    st.subheader("Audit history")
    findings = repository.list_validation_findings(application.id)
    status_events = repository.list_status_events(application.id)
    audit_logs = [
        audit_log
        for audit_log in repository.list_audit_logs()
        if audit_log.application_id == application.id
    ]
    if findings:
        with st.expander("Validation findings"):
            st.write(
                [
                    {
                        "severity": finding.severity,
                        "code": finding.code,
                        "message": finding.message,
                    }
                    for finding in findings
                ]
            )
    if status_events:
        with st.expander("Status events"):
            st.write(
                [
                    {
                        "from": event.from_status,
                        "to": event.to_status,
                        "notes": event.notes,
                        "created_at": event.created_at,
                    }
                    for event in status_events
                ]
            )
    if audit_logs:
        with st.expander("Audit logs"):
            st.write(
                [
                    {
                        "action": audit_log.action,
                        "detail": audit_log.detail,
                        "created_at": audit_log.created_at,
                    }
                    for audit_log in audit_logs
                ]
            )


def _save_review_decision(
    *,
    settings: Settings,
    candidate_email: str,
    vacancy: Vacancy,
    content: GeneratedApplicationContent,
    validation_report: ValidationReport,
    decision: ReviewDecision,
    match_score: float,
    recommendation: str,
    notes: str,
) -> ApplicationRecord | None:
    repository = ApplicationRepository(settings.database_url)
    repository.create_schema()
    try:
        record = repository.record_review_decision(
            candidate_email=candidate_email,
            vacancy=vacancy,
            content=content,
            validation_report=validation_report,
            decision=decision,
            match_score=match_score,
            recommendation=recommendation,
            notes=notes,
        )
    except ApprovalBlockedError as exc:
        st.error(str(exc))
        return None
    except DuplicateApplicationError as exc:
        st.error(str(exc))
        return None
    except RepositoryError as exc:
        st.error(str(exc))
        return None

    st.success(f"Saved {decision.value} application record #{record.id}.")
    return record


def main() -> None:
    """Streamlit entry point."""

    try:
        render_app(Settings())
    except InternshipAgentError as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
