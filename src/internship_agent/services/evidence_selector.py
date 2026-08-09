"""Deterministic evidence selection for vacancy requirements."""

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.domain.evidence import EvidenceItem, EvidenceSelection
from internship_agent.domain.vacancy import Vacancy


def select_evidence(
    candidate: CandidateProfile,
    vacancy: Vacancy,
    evidence_items: list[EvidenceItem],
) -> EvidenceSelection:
    """Map vacancy requirements to approved candidate evidence."""

    selected_by_ref: dict[str, EvidenceItem] = {}
    gaps: list[str] = []
    warnings: list[str] = []
    candidate_skills = candidate.normalized_skills()

    for skill in vacancy.skills:
        normalized_skill = skill.name.casefold()
        matches = [
            item
            for item in evidence_items
            if normalized_skill in item.normalized_keywords()
            or normalized_skill in item.text.casefold()
        ]
        if normalized_skill in candidate_skills:
            matches.extend(item for item in evidence_items if item.source_ref == "candidate.skills")

        if matches:
            for match in matches:
                selected_by_ref[match.source_ref] = match
        else:
            gaps.append(f"No approved evidence for {skill.name}.")

    _select_role_evidence(vacancy, evidence_items, selected_by_ref)
    _select_profile_basics(evidence_items, selected_by_ref)

    if not selected_by_ref:
        warnings.append("No matching approved evidence was found for the vacancy.")

    return EvidenceSelection(
        selected=list(selected_by_ref.values()),
        gaps=_dedupe(gaps),
        warnings=warnings,
    )


def _select_role_evidence(
    vacancy: Vacancy,
    evidence_items: list[EvidenceItem],
    selected_by_ref: dict[str, EvidenceItem],
) -> None:
    role_text = f"{vacancy.role_title} {vacancy.source_text}".casefold()
    for item in evidence_items:
        if any(keyword.casefold() in role_text for keyword in item.keywords):
            selected_by_ref[item.source_ref] = item


def _select_profile_basics(
    evidence_items: list[EvidenceItem],
    selected_by_ref: dict[str, EvidenceItem],
) -> None:
    for source_ref in ("candidate.education", "candidate.internship"):
        for item in evidence_items:
            if item.source_ref == source_ref:
                selected_by_ref[item.source_ref] = item


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
