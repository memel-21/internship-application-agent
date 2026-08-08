"""Tests for vacancy model validation."""

import pytest
from pydantic import ValidationError

from internship_agent.domain.vacancy import RequirementLevel, SkillRequirement, Vacancy


def test_vacancy_can_be_created_manually() -> None:
    """A structured vacancy can be created without AI extraction."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Intern",
        location="Remote",
        source_text="Python and SQL internship for students with software interests.",
        skills=[SkillRequirement(name="Python", level=RequirementLevel.REQUIRED)],
    )

    assert vacancy.company_name == "Acme"
    assert vacancy.normalized_required_skills() == {"python"}


def test_vacancy_rejects_empty_company_name() -> None:
    """Vacancy boundary validation rejects invalid external input."""

    with pytest.raises(ValidationError):
        Vacancy(company_name="", role_title="Intern", location="Remote", source_text="Text")
