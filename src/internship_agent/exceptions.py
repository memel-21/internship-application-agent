"""Domain-specific exceptions for actionable application errors."""


class InternshipAgentError(Exception):
    """Base exception for recoverable application errors."""


class CandidateProfileError(InternshipAgentError):
    """Raised when a candidate profile cannot be loaded or validated."""


class DuplicateApplicationError(InternshipAgentError):
    """Raised when an application duplicates an existing candidate/company/role record."""


class RepositoryError(InternshipAgentError):
    """Raised when persistence fails in a recoverable way."""


class InvalidStatusTransitionError(InternshipAgentError):
    """Raised when an application status transition violates product rules."""
