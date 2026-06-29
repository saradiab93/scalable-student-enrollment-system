class DomainError(Exception):
    """Base exception for domain-level errors."""


class DuplicateEnrollmentError(DomainError):
    """Raised when a student is already enrolled."""


class EnrollmentNotFoundError(DomainError):
    """Raised when an enrollment record cannot be found."""


class InvalidEnrollmentDataError(DomainError):
    """Raised when enrollment payload fails validation."""
