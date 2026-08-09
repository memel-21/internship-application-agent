"""Approved evidence models for grounded application generation."""

from pydantic import BaseModel, ConfigDict, Field


class EvidenceItem(BaseModel):
    """One approved evidence item that can support generated claims."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)

    def normalized_keywords(self) -> set[str]:
        """Return lowercase keywords for deterministic matching."""

        return {keyword.strip().casefold() for keyword in self.keywords if keyword.strip()}


class EvidenceSelection(BaseModel):
    """Selected evidence and unsupported vacancy requirements."""

    model_config = ConfigDict(extra="forbid")

    selected: list[EvidenceItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def source_refs(self) -> set[str]:
        """Return source refs allowed for generated claims."""

        return {item.source_ref for item in self.selected}
