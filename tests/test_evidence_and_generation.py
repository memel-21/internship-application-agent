"""Tests for evidence-grounded content generation."""

from types import SimpleNamespace

import pytest

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.evidence import EvidenceItem, EvidenceSelection
from internship_agent.domain.generated_content import (
    GeneratedApplicationContent,
    GeneratedClaim,
)
from internship_agent.domain.vacancy import RequirementLevel, SkillRequirement, Vacancy
from internship_agent.exceptions import UnsupportedClaimError
from internship_agent.services.content_generator import (
    DemoContentGenerator,
    OpenAIContentGenerator,
    validate_generated_content_sources,
)
from internship_agent.services.evidence_loader import load_approved_evidence
from internship_agent.services.evidence_selector import select_evidence


def test_load_approved_evidence_from_profile_and_project_file(
    candidate_profile: CandidateProfile,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Approved evidence loads from profile fields and project evidence markdown."""

    evidence_path = tmp_path / "documents" / "project_evidence.md"
    evidence_path.parent.mkdir()
    evidence_path.write_text(
        """
        # Approved Candidate Evidence

        ## Final Year Project

        Built an Autoencoder prototype using Python, TensorFlow and Streamlit.
        """,
        encoding="utf-8",
    )
    candidate = candidate_profile.model_copy(
        update={
            "documents": candidate_profile.documents.model_copy(
                update={"project_evidence": evidence_path.relative_to(tmp_path)}
            )
        }
    )

    evidence = load_approved_evidence(candidate, base_path=tmp_path)

    assert any(item.source_ref == "candidate.skills" for item in evidence)
    assert any("Autoencoder" in item.keywords for item in evidence)


def test_select_evidence_maps_requirements_and_records_gaps(
    candidate_profile: CandidateProfile,
) -> None:
    """Evidence selector maps supported skills and records unsupported requirements."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Machine Learning Intern",
        source_text="Python and AWS internship source text with enough detail.",
        skills=[
            SkillRequirement(name="Python", level=RequirementLevel.REQUIRED),
            SkillRequirement(name="AWS", level=RequirementLevel.PREFERRED),
        ],
    )
    evidence = [
        EvidenceItem(
            evidence_id="candidate.skills",
            title="Skills",
            text="Python, SQL",
            source_ref="candidate.skills",
            keywords=["Python", "SQL"],
        )
    ]

    selection = select_evidence(candidate_profile, vacancy, evidence)

    assert "candidate.skills" in selection.source_refs()
    assert selection.gaps == ["No approved evidence for AWS."]


def test_demo_content_generator_creates_grounded_editable_content(
    candidate_profile: CandidateProfile,
) -> None:
    """Demo generator creates content with internal claim source refs."""

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Engineering Intern",
        source_text="Python internship source text with enough detail.",
        skills=[SkillRequirement(name="Python", level=RequirementLevel.REQUIRED)],
    )
    selection = EvidenceSelection(
        selected=[
            EvidenceItem(
                evidence_id="candidate.skills",
                title="Skills",
                text="Python",
                source_ref="candidate.skills",
                keywords=["Python"],
            )
        ]
    )

    content = DemoContentGenerator().generate(
        candidate=candidate_profile,
        vacancy=vacancy,
        evidence_selection=selection,
    )

    assert content.email_subject == "Application for Software Engineering Intern - Test Student"
    assert "source" not in content.cover_letter.casefold()
    assert content.claims[0].source_refs


def test_generated_content_rejects_exposed_internal_source_refs() -> None:
    """User-facing content cannot expose internal source markers."""

    with pytest.raises(ValueError, match="internal source refs"):
        GeneratedApplicationContent(
            professional_summary="Summary",
            cover_letter="I used Python. [source: candidate.skills]",
            email_subject="Application",
            email_body="Body",
            claims=[GeneratedClaim(text="I used Python.", source_refs=["candidate.skills"])],
        )


def test_validate_generated_content_rejects_unsupported_claim_refs() -> None:
    """Unsupported claim source refs are rejected."""

    content = GeneratedApplicationContent(
        professional_summary="Summary",
        cover_letter="I used Python.",
        email_subject="Application",
        email_body="Body",
        claims=[GeneratedClaim(text="I deployed on AWS.", source_refs=["candidate.aws"])],
    )
    selection = EvidenceSelection(selected=[])

    with pytest.raises(UnsupportedClaimError, match="unsupported source"):
        validate_generated_content_sources(content, selection)


def test_openai_content_generator_uses_structured_output_with_mock_client(
    candidate_profile: CandidateProfile,
) -> None:
    """OpenAI content generator requests structured output and validates sources."""

    class Responses:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] | None = None

        def create(self, **kwargs: object) -> SimpleNamespace:
            self.kwargs = kwargs
            return SimpleNamespace(
                output_text=(
                    '{"professional_summary":"Summary","selected_skills":["Python"],'
                    '"cover_letter":"Dear Acme, I used Python.","email_subject":"Application",'
                    '"email_body":"Dear Acme, I used Python.",'
                    '"claims":[{"text":"I used Python.","source_refs":["candidate.skills"]}],'
                    '"gaps":[],"warnings":[]}'
                )
            )

    vacancy = Vacancy(
        company_name="Acme",
        role_title="Software Engineering Intern",
        source_text="Python internship source text with enough detail.",
    )
    selection = EvidenceSelection(
        selected=[
            EvidenceItem(
                evidence_id="candidate.skills",
                title="Skills",
                text="Python",
                source_ref="candidate.skills",
                keywords=["Python"],
            )
        ]
    )
    responses = Responses()
    generator = OpenAIContentGenerator(
        api_key="test-key",
        model="test-model",
        client=SimpleNamespace(responses=responses),
    )

    content = generator.generate(
        candidate=candidate_profile,
        vacancy=vacancy,
        evidence_selection=selection,
    )

    assert content.selected_skills == ["Python"]
    assert responses.kwargs is not None
    assert responses.kwargs["model"] == "test-model"
