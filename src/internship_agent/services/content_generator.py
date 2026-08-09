"""Grounded application content generation services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.evidence import EvidenceSelection
from internship_agent.domain.generated_content import (
    GeneratedApplicationContent,
    GeneratedClaim,
)
from internship_agent.domain.vacancy import Vacancy
from internship_agent.exceptions import ContentGenerationError, UnsupportedClaimError


class ApplicationContentGenerator(Protocol):
    """Protocol for grounded application content generators."""

    def generate(
        self,
        *,
        candidate: CandidateProfile,
        vacancy: Vacancy,
        evidence_selection: EvidenceSelection,
    ) -> GeneratedApplicationContent:
        """Generate grounded application content for human review."""


class DemoContentGenerator:
    """Deterministic content generator for demo mode and tests."""

    def generate(
        self,
        *,
        candidate: CandidateProfile,
        vacancy: Vacancy,
        evidence_selection: EvidenceSelection,
    ) -> GeneratedApplicationContent:
        """Generate conservative grounded content without an API call."""

        selected_skills = _selected_skills(candidate, vacancy)
        source_refs = sorted(evidence_selection.source_refs())
        if not source_refs:
            raise UnsupportedClaimError("Cannot generate content without selected evidence.")

        summary = (
            f"{candidate.full_name} is an information systems student at "
            f"{candidate.university} with verified skills relevant to {vacancy.role_title}."
        )
        claims = [
            GeneratedClaim(text=summary, source_refs=["candidate.education", "candidate.skills"]),
            GeneratedClaim(
                text=(
                    "The candidate is available from "
                    f"{candidate.internship.start_date.isoformat()} "
                    f"to {candidate.internship.end_date.isoformat()}."
                ),
                source_refs=["candidate.internship"],
            ),
        ]

        skill_sentence = (
            f"My most relevant verified skills for this role are {', '.join(selected_skills)}."
            if selected_skills
            else (
                "I have reviewed the vacancy requirements and would focus on the "
                "verified evidence available."
            )
        )
        gap_sentence = (
            f"I also recognise the current evidence gaps: {'; '.join(evidence_selection.gaps)}"
            if evidence_selection.gaps
            else "The selected evidence aligns with the stated vacancy requirements."
        )

        cover_letter = "\n\n".join(
            [
                f"Dear {vacancy.company_name} Hiring Team,",
                (
                    f"I am applying for the {vacancy.role_title} position at "
                    f"{vacancy.company_name}. {summary}"
                ),
                (
                    f"{skill_sentence} My internship availability is from "
                    f"{candidate.internship.start_date.isoformat()} to "
                    f"{candidate.internship.end_date.isoformat()}, matching the period "
                    "recorded in my verified profile."
                ),
                gap_sentence,
                "Thank you for considering my application.",
                f"Sincerely,\n{candidate.full_name}",
            ]
        )
        email_body = (
            f"Dear {vacancy.company_name} Hiring Team,\n\n"
            f"I would like to apply for the {vacancy.role_title} position. "
            f"{skill_sentence} My approved profile records internship availability from "
            f"{candidate.internship.start_date.isoformat()} to "
            f"{candidate.internship.end_date.isoformat()}.\n\n"
            "Thank you for your consideration.\n\n"
            f"Regards,\n{candidate.full_name}"
        )

        content = GeneratedApplicationContent(
            professional_summary=summary,
            selected_skills=selected_skills,
            cover_letter=cover_letter,
            email_subject=f"Application for {vacancy.role_title} - {candidate.full_name}",
            email_body=email_body,
            claims=claims,
            gaps=evidence_selection.gaps,
            warnings=evidence_selection.warnings,
        )
        validate_generated_content_sources(content, evidence_selection)
        return content


class OpenAIContentGenerator:
    """OpenAI-backed content generator using structured output."""

    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        """Create an OpenAI-backed content generator."""

        self._client = client or OpenAI(api_key=api_key)
        self._model = model
        self._prompt = _load_prompt()

    def generate(
        self,
        *,
        candidate: CandidateProfile,
        vacancy: Vacancy,
        evidence_selection: EvidenceSelection,
    ) -> GeneratedApplicationContent:
        """Generate grounded content using the Responses API."""

        try:
            response = self._client.responses.create(
                model=self._model,
                input=[
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "candidate": candidate.model_dump(mode="json"),
                                "vacancy": vacancy.model_dump(mode="json"),
                                "selected_evidence": [
                                    item.model_dump(mode="json")
                                    for item in evidence_selection.selected
                                ],
                                "gaps": evidence_selection.gaps,
                            }
                        ),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "generated_application_content",
                        "schema": GeneratedApplicationContent.model_json_schema(),
                        "strict": False,
                    }
                },
            )
        except RateLimitError as exc:
            raise ContentGenerationError("OpenAI rate limit reached. Try again later.") from exc
        except APIStatusError as exc:
            raise ContentGenerationError(
                f"OpenAI content generation failed with status {exc.status_code}."
            ) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise ContentGenerationError("Could not reach OpenAI for content generation.") from exc

        content = parse_generated_content_payload(_response_text(response))
        validate_generated_content_sources(content, evidence_selection)
        return content


def create_content_generator(
    *, demo_mode: bool, api_key: str | None, model: str
) -> ApplicationContentGenerator:
    """Create the configured content generator."""

    if demo_mode:
        return DemoContentGenerator()
    if not api_key:
        raise ContentGenerationError("OPENAI_API_KEY is required when demo mode is disabled.")
    return OpenAIContentGenerator(api_key=api_key, model=model)


def parse_generated_content_payload(payload: str | dict[str, Any]) -> GeneratedApplicationContent:
    """Parse and validate structured generated content."""

    try:
        raw_payload: Any = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError as exc:
        raise ContentGenerationError("Model returned invalid generated-content JSON.") from exc
    try:
        return GeneratedApplicationContent.model_validate(raw_payload)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {"loc": ["content"], "msg": "invalid"}
        location = ".".join(str(part) for part in first_error["loc"])
        raise ContentGenerationError(
            f"Generated content failed validation at '{location}': {first_error['msg']}."
        ) from exc


def validate_generated_content_sources(
    content: GeneratedApplicationContent,
    evidence_selection: EvidenceSelection,
) -> None:
    """Reject generated claims that lack approved evidence source references."""

    allowed_refs = evidence_selection.source_refs()
    required_profile_refs = {"candidate.education", "candidate.skills", "candidate.internship"}
    allowed_refs = allowed_refs | required_profile_refs
    for claim in content.claims:
        unsupported_refs = [ref for ref in claim.source_refs if ref not in allowed_refs]
        if unsupported_refs:
            raise UnsupportedClaimError(
                f"Generated claim has unsupported source references: {', '.join(unsupported_refs)}."
            )
        if not claim.source_refs:
            raise UnsupportedClaimError("Generated claim is missing source references.")


def _selected_skills(candidate: CandidateProfile, vacancy: Vacancy) -> list[str]:
    candidate_skills = candidate.normalized_skills()
    vacancy_skills = [skill.name for skill in vacancy.skills]
    selected = [skill for skill in vacancy_skills if skill.casefold() in candidate_skills]
    return selected[:6]


def _load_prompt() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "content_generation.md"
    return path.read_text(encoding="utf-8")


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    raise ContentGenerationError("OpenAI response did not include output text.")
