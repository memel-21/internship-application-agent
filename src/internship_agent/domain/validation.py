"""Validation finding schemas for generated application content."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FindingSeverity(StrEnum):
    """Validation finding severity."""

    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATION = "information"


class ValidationFinding(BaseModel):
    """One deterministic content validation finding."""

    model_config = ConfigDict(extra="forbid")

    severity: FindingSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ValidationReport(BaseModel):
    """Content validation report."""

    model_config = ConfigDict(extra="forbid")

    findings: list[ValidationFinding] = Field(default_factory=list)

    @property
    def has_blocking_findings(self) -> bool:
        """Return whether approval must be blocked."""

        return any(finding.severity == FindingSeverity.BLOCKING for finding in self.findings)
