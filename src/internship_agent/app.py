"""Minimal Streamlit interface for local vacancy analysis."""

from datetime import date
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from internship_agent.domain.evidence import EvidenceSelection
from internship_agent.domain.generated_content import GeneratedApplicationContent
from internship_agent.domain.review import ReviewDecision
from internship_agent.domain.vacancy import RequirementLevel, SkillRequirement, Vacancy
from internship_agent.domain.validation import FindingSeverity, ValidationReport
from internship_agent.exceptions import (
    ApprovalBlockedError,
    CandidateProfileError,
    ContentGenerationError,
    DuplicateApplicationError,
    EvidenceError,
    InternshipAgentError,
    RepositoryError,
    VacancyExtractionError,
)
from internship_agent.persistence.models import ApplicationRecord
from internship_agent.persistence.repository import ApplicationRepository
from internship_agent.services.content_generator import create_content_generator
from internship_agent.services.content_validator import validate_application_content
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

    st.caption("Milestone 4: grounded generation with deterministic content validation.")

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

    if settings.demo_mode:
        st.info("Demo mode is enabled, so vacancy extraction uses deterministic local logic.")
    else:
        st.info("Demo mode is disabled. Vacancy extraction uses the OpenAI Responses API.")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
