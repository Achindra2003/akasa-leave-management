"""Domain errors.

Each error carries a stable machine-readable ``code`` and a human-friendly ``message``.
The API layer maps them to RFC 9457 Problem Details; the UI shows ``message`` verbatim,
so messages are written for end users, not developers.
"""

from typing import Any


class DomainError(Exception):
    status_code: int = 400
    code: str = "domain_error"
    title: str = "Request could not be processed"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationFailed(DomainError):
    status_code = 422
    code = "validation_failed"
    title = "Some details need fixing"


class DocumentsRequired(ValidationFailed):
    code = "documents_required"
    title = "Supporting documents required"


class OverlappingLeave(DomainError):
    status_code = 409
    code = "overlapping_leave"
    title = "Overlapping leave"


class InvalidTransition(DomainError):
    status_code = 409
    code = "invalid_transition"
    title = "This action is no longer available"


class StaleRequest(DomainError):
    status_code = 409
    code = "stale_request"
    title = "Someone else updated this request"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"
    title = "Not found"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"
    title = "You don't have access to this"


class NoApproverAvailable(DomainError):
    status_code = 422
    code = "no_approver_available"
    title = "No approver available"


class AuthenticationFailed(DomainError):
    status_code = 401
    code = "authentication_failed"
    title = "Sign-in required"
