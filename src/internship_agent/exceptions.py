"""Domain-specific exceptions for actionable application errors."""


class InternshipAgentError(Exception):
    """Base exception for recoverable application errors."""


class CandidateProfileError(InternshipAgentError):
    """Raised when a candidate profile cannot be loaded or validated."""


class VacancyExtractionError(InternshipAgentError):
    """Raised when vacancy extraction fails safely."""


class VacancyExtractionAuthError(VacancyExtractionError):
    """Raised when OpenAI authentication fails."""


class VacancyExtractionRateLimitError(VacancyExtractionError):
    """Raised when the OpenAI API returns a rate-limit response."""


class VacancyExtractionNetworkError(VacancyExtractionError):
    """Raised when transient network failures prevent extraction."""


class VacancyExtractionValidationError(VacancyExtractionError):
    """Raised when extracted vacancy data fails schema validation."""


class EvidenceError(InternshipAgentError):
    """Raised when approved evidence cannot be loaded safely."""


class ContentGenerationError(InternshipAgentError):
    """Raised when application content generation fails safely."""


class UnsupportedClaimError(ContentGenerationError):
    """Raised when generated content contains unsupported claims."""


class DuplicateApplicationError(InternshipAgentError):
    """Raised when an application duplicates an existing candidate/company/role record."""


class RepositoryError(InternshipAgentError):
    """Raised when persistence fails in a recoverable way."""


class InvalidStatusTransitionError(InternshipAgentError):
    """Raised when an application status transition violates product rules."""


class ApprovalBlockedError(InternshipAgentError):
    """Raised when a package cannot be approved due to blocking validation findings."""


class DocumentGenerationError(InternshipAgentError):
    """Raised when approved application documents cannot be generated safely."""


class EmailDraftError(InternshipAgentError):
    """Raised when an email draft package cannot be prepared safely."""
