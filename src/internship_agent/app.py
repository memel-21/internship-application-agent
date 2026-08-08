"""Minimal Streamlit interface for local vacancy analysis."""

from datetime import date
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from internship_agent.domain.vacancy import RequirementLevel, SkillRequirement, Vacancy
from internship_agent.exceptions import (
    CandidateProfileError,
    InternshipAgentError,
    VacancyExtractionError,
)
from internship_agent.services.profile_loader import load_candidate_profile
from internship_agent.services.vacancy_extractor import create_vacancy_extractor
from internship_agent.settings import Settings


def render_app(settings: Settings) -> None:
    """Render the Milestone 1 Streamlit application."""

    st.set_page_config(page_title="Internship Application Agent", layout="wide")
    st.title("Internship Application Agent")

    st.caption("Milestone 2: profile loading and structured vacancy extraction.")

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

    if settings.demo_mode:
        st.info("Demo mode is enabled, so vacancy extraction uses deterministic local logic.")
    else:
        st.info("Demo mode is disabled. Vacancy extraction uses the OpenAI Responses API.")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    """Streamlit entry point."""

    try:
        render_app(Settings())
    except InternshipAgentError as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
