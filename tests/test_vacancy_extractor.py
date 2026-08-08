"""Tests for structured vacancy extraction."""

from types import SimpleNamespace

import pytest
from openai import APIConnectionError

from internship_agent.domain.vacancy import EmploymentMode, RequirementLevel
from internship_agent.exceptions import (
    VacancyExtractionAuthError,
    VacancyExtractionNetworkError,
    VacancyExtractionValidationError,
)
from internship_agent.services.vacancy_extractor import (
    DemoVacancyExtractor,
    OpenAIVacancyExtractor,
    create_vacancy_extractor,
    parse_vacancy_payload,
)


def test_demo_extractor_returns_valid_vacancy() -> None:
    """Demo extractor produces a validated vacancy without network access."""

    vacancy = DemoVacancyExtractor().extract(
        """
        Company: Example AI
        Role: Machine Learning Intern
        Location: Shah Alam
        Hybrid internship for students.
        Responsibilities:
        - Build Python and SQL data tools.
        Eligibility:
        - Must be a current student.
        Apply by email.
        """
    )

    assert vacancy.company_name == "Example AI"
    assert vacancy.role_title == "Machine Learning Intern"
    assert vacancy.employment_mode == EmploymentMode.HYBRID
    assert "python" in vacancy.normalized_required_skills()


def test_demo_extractor_adds_missing_information_warnings() -> None:
    """Missing vacancy fields produce warnings instead of fabricated facts."""

    vacancy = DemoVacancyExtractor().extract(
        "A short internship advertisement for Python data work with no clear employer."
    )

    assert vacancy.company_name == "Unknown company"
    assert "Company name was missing or unclear." in vacancy.extraction_warnings
    assert "Application channel was missing." in vacancy.extraction_warnings
    assert "Eligibility requirements were unclear." in vacancy.extraction_warnings


def test_parse_vacancy_payload_rejects_malformed_json() -> None:
    """Malformed model output is rejected safely."""

    with pytest.raises(VacancyExtractionValidationError, match="invalid JSON"):
        parse_vacancy_payload("{not json", source_text="Valid source text for parsing.")


def test_parse_vacancy_payload_preserves_original_source_text() -> None:
    """Original advertisement text overrides model-provided source text."""

    vacancy = parse_vacancy_payload(
        {
            "company_name": "Acme",
            "role_title": "Software Engineering Intern",
            "source_text": "model changed this text",
            "skills": [{"name": "Python", "level": RequirementLevel.REQUIRED.value}],
        },
        source_text="Original vacancy advertisement with enough detail.",
    )

    assert vacancy.source_text == "Original vacancy advertisement with enough detail."


def test_create_openai_extractor_requires_api_key_when_demo_disabled() -> None:
    """Real extraction mode requires an API key at construction boundary."""

    with pytest.raises(VacancyExtractionAuthError):
        create_vacancy_extractor(demo_mode=False, api_key=None, model="test-model")


def test_openai_extractor_uses_structured_output_with_mock_client() -> None:
    """OpenAI adapter requests JSON-schema structured output and validates response."""

    class Responses:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] | None = None

        def create(self, **kwargs: object) -> SimpleNamespace:
            self.kwargs = kwargs
            return SimpleNamespace(
                output_text=(
                    '{"company_name":"Acme","role_title":"Software Engineering Intern",'
                    '"skills":[{"name":"Python","level":"required"}],'
                    '"source_text":"model source"}'
                )
            )

    responses = Responses()
    client = SimpleNamespace(responses=responses)
    extractor = OpenAIVacancyExtractor(api_key="test-key", model="test-model", client=client)

    vacancy = extractor.extract("Original Python internship vacancy source text.")

    assert vacancy.company_name == "Acme"
    assert vacancy.source_text == "Original Python internship vacancy source text."
    assert responses.kwargs is not None
    assert responses.kwargs["model"] == "test-model"
    assert responses.kwargs["text"] == {
        "format": {
            "type": "json_schema",
            "name": "vacancy",
            "schema": vacancy.__class__.model_json_schema(),
            "strict": False,
        }
    }


def test_openai_extractor_retries_transient_network_errors() -> None:
    """Transient network failures are retried and then reported clearly."""

    class Responses:
        def create(self, **_kwargs: object) -> object:
            request = object()
            raise APIConnectionError(request=request)

    client = SimpleNamespace(responses=Responses())
    extractor = OpenAIVacancyExtractor(
        api_key="test-key",
        model="test-model",
        client=client,
        max_retries=1,
    )

    with pytest.raises(VacancyExtractionNetworkError):
        extractor.extract("Original Python internship vacancy source text.")
