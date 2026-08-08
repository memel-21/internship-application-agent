"""Structured vacancy extraction services."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError

from internship_agent.domain.vacancy import (
    EmploymentMode,
    RequirementLevel,
    SkillRequirement,
    Vacancy,
)
from internship_agent.exceptions import (
    VacancyExtractionAuthError,
    VacancyExtractionError,
    VacancyExtractionNetworkError,
    VacancyExtractionRateLimitError,
    VacancyExtractionValidationError,
)


class VacancyExtractor(Protocol):
    """Protocol for vacancy extraction implementations."""

    def extract(self, vacancy_text: str) -> Vacancy:
        """Extract a validated structured vacancy."""


class DemoVacancyExtractor:
    """Deterministic extractor for demo mode and tests."""

    def extract(self, vacancy_text: str) -> Vacancy:
        """Extract a conservative vacancy from pasted text without an API call."""

        text = _validate_source_text(vacancy_text)
        warnings = _deterministic_warnings(text)
        company = _extract_labeled_value(text, "company") or "Unknown company"
        role = _extract_labeled_value(text, "role") or _extract_labeled_value(text, "title")
        role = role or "Unknown internship role"
        employment_mode = _employment_mode(text)

        skills = _extract_demo_skills(text)
        location = _extract_labeled_value(text, "location")

        return Vacancy(
            company_name=company,
            role_title=role,
            location=location,
            employment_mode=employment_mode,
            responsibilities=_extract_bullets(text, "responsibilities"),
            skills=skills,
            education_requirements=_extract_bullets(text, "education"),
            eligibility_requirements=_extract_bullets(text, "eligibility"),
            source_text=text,
            extraction_warnings=warnings,
        )


class OpenAIVacancyExtractor:
    """OpenAI Responses API vacancy extractor using structured output."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any | None = None,
        max_retries: int = 2,
    ) -> None:
        """Create an OpenAI-backed extractor."""

        self._client = client or OpenAI(api_key=api_key)
        self._model = model
        self._max_retries = max_retries
        self._prompt = _load_prompt()

    def extract(self, vacancy_text: str) -> Vacancy:
        """Extract a structured vacancy using the Responses API."""

        text = _validate_source_text(vacancy_text)
        last_network_error: VacancyExtractionNetworkError | None = None

        for _attempt in range(self._max_retries + 1):
            try:
                response = self._client.responses.create(
                    model=self._model,
                    input=[
                        {"role": "system", "content": self._prompt},
                        {"role": "user", "content": text},
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "vacancy",
                            "schema": Vacancy.model_json_schema(),
                            "strict": False,
                        }
                    },
                )
                return parse_vacancy_payload(_response_text(response), source_text=text)
            except RateLimitError as exc:
                raise VacancyExtractionRateLimitError(
                    "OpenAI rate limit reached. Try again later or use demo mode."
                ) from exc
            except APIStatusError as exc:
                if exc.status_code in {401, 403}:
                    raise VacancyExtractionAuthError(
                        "OpenAI authentication failed. Check your API key."
                    ) from exc
                if 500 <= exc.status_code < 600:
                    last_network_error = VacancyExtractionNetworkError(
                        "OpenAI service is temporarily unavailable. Try again later."
                    )
                    continue
                raise VacancyExtractionError(
                    f"OpenAI extraction failed with status {exc.status_code}."
                ) from exc
            except (APIConnectionError, APITimeoutError):
                last_network_error = VacancyExtractionNetworkError(
                    "Could not reach OpenAI. Check your network or use demo mode."
                )
                continue

        if last_network_error is not None:
            raise last_network_error
        raise VacancyExtractionError("OpenAI extraction failed.")


def create_vacancy_extractor(
    *, demo_mode: bool, api_key: str | None, model: str
) -> VacancyExtractor:
    """Create the configured vacancy extractor."""

    if demo_mode:
        return DemoVacancyExtractor()
    if not api_key:
        raise VacancyExtractionAuthError("OPENAI_API_KEY is required when demo mode is disabled.")
    return OpenAIVacancyExtractor(api_key=api_key, model=model)


def parse_vacancy_payload(payload: str | Mapping[str, Any], *, source_text: str) -> Vacancy:
    """Parse and validate vacancy data from a model response payload."""

    try:
        raw_payload: Any = json.loads(payload) if isinstance(payload, str) else dict(payload)
    except json.JSONDecodeError as exc:
        raise VacancyExtractionValidationError("Model returned invalid JSON.") from exc

    if not isinstance(raw_payload, dict):
        raise VacancyExtractionValidationError("Model returned a non-object JSON payload.")

    raw_payload["source_text"] = source_text
    raw_payload.setdefault("extraction_warnings", [])
    try:
        vacancy = Vacancy.model_validate(raw_payload)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {"loc": ["vacancy"], "msg": "invalid"}
        location = ".".join(str(part) for part in first_error["loc"])
        raise VacancyExtractionValidationError(
            f"Extracted vacancy failed validation at '{location}': {first_error['msg']}."
        ) from exc

    warnings = [*vacancy.extraction_warnings, *_deterministic_warnings(source_text, vacancy)]
    return vacancy.model_copy(update={"extraction_warnings": _dedupe(warnings)})


def _validate_source_text(vacancy_text: str) -> str:
    text = vacancy_text.strip()
    if len(text) < 20:
        raise VacancyExtractionValidationError("Vacancy text must be at least 20 characters.")
    return text


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    raise VacancyExtractionValidationError("OpenAI response did not include output text.")


def _load_prompt() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "vacancy_extraction.md"
    return path.read_text(encoding="utf-8")


def _extract_labeled_value(text: str, label: str) -> str | None:
    pattern = rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _employment_mode(text: str) -> EmploymentMode:
    normalized = text.casefold()
    if "remote" in normalized:
        return EmploymentMode.REMOTE
    if "hybrid" in normalized:
        return EmploymentMode.HYBRID
    if "onsite" in normalized or "on-site" in normalized:
        return EmploymentMode.ONSITE
    return EmploymentMode.UNKNOWN


def _extract_demo_skills(text: str) -> list[SkillRequirement]:
    known_skills = [
        "Python",
        "SQL",
        "Machine Learning",
        "TensorFlow",
        "Keras",
        "Streamlit",
        "Power BI",
        "Excel",
        "AWS",
    ]
    normalized = text.casefold()
    skills: list[SkillRequirement] = []
    for skill in known_skills:
        if skill.casefold() in normalized:
            level = (
                RequirementLevel.PREFERRED
                if re.search(rf"preferred[^.:\n]*{re.escape(skill)}", text, re.IGNORECASE)
                else RequirementLevel.REQUIRED
            )
            skills.append(SkillRequirement(name=skill, level=level, evidence_text=skill))
    return skills


def _extract_bullets(text: str, heading: str) -> list[str]:
    pattern = rf"(?ims)^\s*{re.escape(heading)}\s*:?\s*(.*?)(?:\n\S[^:\n]{{0,60}}:\s*$|\Z)"
    match = re.search(pattern, text)
    if not match:
        return []
    section = match.group(1)
    return [
        line.strip(" -*\t") for line in section.splitlines() if line.strip().startswith(("-", "*"))
    ]


def _deterministic_warnings(text: str, vacancy: Vacancy | None = None) -> list[str]:
    warnings: list[str] = []
    target = vacancy
    if (
        target is None or target.company_name.casefold() == "unknown company"
    ) and _extract_labeled_value(text, "company") is None:
        warnings.append("Company name was missing or unclear.")
    if (
        (target is None or (not target.application_email and not target.application_url))
        and "apply" not in text.casefold()
        and "email" not in text.casefold()
    ):
        warnings.append("Application channel was missing.")
    if (
        (target is None or not target.eligibility_requirements)
        and "eligible" not in text.casefold()
        and "student" not in text.casefold()
    ):
        warnings.append("Eligibility requirements were unclear.")
    if _has_ambiguous_date(text):
        warnings.append("Dates were ambiguous and need manual review.")
    return warnings


def _has_ambiguous_date(text: str) -> bool:
    return bool(re.search(r"\b\d{1,2}[/-]\d{1,2}(?![/-]\d{2,4})\b", text))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
