"""Load approved candidate evidence for grounded generation."""

from pathlib import Path

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.evidence import EvidenceItem


def load_approved_evidence(candidate: CandidateProfile, *, base_path: Path) -> list[EvidenceItem]:
    """Load approved evidence from the candidate profile and local evidence files."""

    evidence = [
        EvidenceItem(
            evidence_id="candidate.education",
            title="Education",
            text=(
                f"{candidate.education.programme} at {candidate.education.institution}; "
                f"CGPA {candidate.education.cgpa:.2f} out of {candidate.education.cgpa_scale:.2f}; "
                f"{'; '.join(candidate.education.academic_highlights)}"
            ),
            source_ref="candidate.education",
            keywords=[
                candidate.education.programme,
                candidate.education.institution,
                "CGPA",
                *candidate.education.academic_highlights,
            ],
        ),
        EvidenceItem(
            evidence_id="candidate.skills",
            title="Verified skills",
            text=", ".join(candidate.flattened_skills()),
            source_ref="candidate.skills",
            keywords=candidate.flattened_skills(),
        ),
        EvidenceItem(
            evidence_id="candidate.internship",
            title="Internship availability",
            text=(
                f"Available from {candidate.internship.start_date.isoformat()} to "
                f"{candidate.internship.end_date.isoformat()} for "
                f"{candidate.internship.duration_weeks} weeks."
            ),
            source_ref="candidate.internship",
            keywords=[
                candidate.internship.start_date.isoformat(),
                candidate.internship.end_date.isoformat(),
                "internship availability",
            ],
        ),
    ]

    project_evidence_path = base_path / candidate.documents.project_evidence
    if project_evidence_path.exists():
        evidence.extend(_markdown_evidence_items(project_evidence_path))

    return evidence


def _markdown_evidence_items(path: Path) -> list[EvidenceItem]:
    text = path.read_text(encoding="utf-8")
    sections = _split_markdown_sections(text)
    items: list[EvidenceItem] = []
    for index, (heading, body) in enumerate(sections, start=1):
        clean_body = body.strip()
        if not clean_body:
            continue
        evidence_id = f"project_evidence.{index}"
        items.append(
            EvidenceItem(
                evidence_id=evidence_id,
                title=heading,
                text=clean_body,
                source_ref=evidence_id,
                keywords=_keywords_from_text(f"{heading} {clean_body}"),
            )
        )
    return items


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = "Project evidence"
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines)))
            current_heading = line.removeprefix("## ").strip()
            current_lines = []
        elif current_heading:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines)))
    return sections


def _keywords_from_text(text: str) -> list[str]:
    known_terms = [
        "Python",
        "SQL",
        "TensorFlow",
        "Keras",
        "Streamlit",
        "scikit-learn",
        "pandas",
        "NumPy",
        "Autoencoder",
        "Isolation Forest",
        "Machine Learning",
        "Data Preprocessing",
        "Feature Engineering",
        "Model Evaluation",
        "Power BI",
    ]
    normalized = text.casefold()
    return [term for term in known_terms if term.casefold() in normalized]
