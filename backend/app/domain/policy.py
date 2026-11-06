"""Leave policy: pure functions, no I/O.

Policy is *data* (``LeavePolicy``) so thresholds can change per org/env without code
changes (see DECISIONS.md D-002). Every rule here is mirrored client-side for instant
feedback, but this module is the authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.domain.errors import DocumentsRequired, ValidationFailed

ALLOWED_DOCUMENT_TYPES: frozenset[str] = frozenset({"application/pdf", "image/png", "image/jpeg"})


@dataclass(frozen=True, slots=True)
class LeavePolicy:
    # "More than N consecutive days" triggers documents + 2-level approval (brief: N = 3).
    escalation_threshold_days: int = 3
    max_span_days: int = 30
    max_advance_days: int = 365
    reason_min_len: int = 5
    reason_max_len: int = 500
    max_document_bytes: int = 5 * 1024 * 1024
    max_documents: int = 5
    allowed_document_types: frozenset[str] = field(default=ALLOWED_DOCUMENT_TYPES)


DEFAULT_POLICY = LeavePolicy()


def calendar_days(from_date: date, to_date: date) -> int:
    """Inclusive calendar-day count. Nov 1 -> Nov 5 == 5 (D-002)."""
    return (to_date - from_date).days + 1


def working_days(from_date: date, to_date: date) -> int:
    """Mon-Fri count, shown in the UI for information only."""
    days, d = 0, from_date
    while d <= to_date:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def requires_escalation(total_days: int, policy: LeavePolicy = DEFAULT_POLICY) -> bool:
    """True when the request needs documents AND Manager -> HOD approval."""
    return total_days > policy.escalation_threshold_days


@dataclass(frozen=True, slots=True)
class DocumentMeta:
    filename: str
    content_type: str
    size: int


def validate_leave_request(
    *,
    from_date: date,
    to_date: date,
    reason: str,
    today: date,
    documents: list[DocumentMeta] | None = None,
    policy: LeavePolicy = DEFAULT_POLICY,
) -> int:
    """Validate a new leave request. Returns total calendar days.

    Collects *all* field errors before raising, so the user fixes everything in one pass.
    """
    errors: dict[str, str] = {}
    documents = documents or []

    if to_date < from_date:
        errors["toDate"] = "End date can't be before the start date."
    if from_date < today:
        errors["fromDate"] = "Leave can't start in the past."
    elif (from_date - today).days > policy.max_advance_days:
        errors["fromDate"] = (
            f"Leave can be applied at most {policy.max_advance_days} days in advance."
        )

    total = calendar_days(from_date, to_date) if to_date >= from_date else 0
    if total > policy.max_span_days:
        errors["toDate"] = (
            f"A single request can cover at most {policy.max_span_days} days "
            f"(this one covers {total}). Please split it into separate requests."
        )

    stripped = reason.strip()
    if len(stripped) < policy.reason_min_len:
        errors["reason"] = f"Please give a reason of at least {policy.reason_min_len} characters."
    elif len(stripped) > policy.reason_max_len:
        errors["reason"] = f"Reason must be under {policy.reason_max_len} characters."

    doc_errors = validate_documents(documents, policy)
    if doc_errors:
        errors["documents"] = doc_errors

    if errors:
        raise ValidationFailed("Please fix the highlighted fields.", details={"fields": errors})

    if requires_escalation(total, policy) and not documents:
        raise DocumentsRequired(
            f"Leave longer than {policy.escalation_threshold_days} consecutive days needs a "
            "supporting document (e.g. medical certificate) and is approved by your "
            "Manager and then your HOD.",
            details={"fields": {"documents": "Attach at least one document."}, "totalDays": total},
        )
    return total


def validate_documents(documents: list[DocumentMeta], policy: LeavePolicy = DEFAULT_POLICY) -> str:
    """Return a user-facing error string, or '' if all documents are acceptable."""
    if len(documents) > policy.max_documents:
        return f"You can attach at most {policy.max_documents} files."
    for doc in documents:
        if doc.content_type not in policy.allowed_document_types:
            return f"'{doc.filename}' isn't supported. Please upload a PDF, PNG or JPG."
        if doc.size == 0:
            return f"'{doc.filename}' is empty."
        if doc.size > policy.max_document_bytes:
            mb = policy.max_document_bytes // (1024 * 1024)
            return f"'{doc.filename}' is larger than {mb} MB."
    return ""


def ranges_overlap(a_from: date, a_to: date, b_from: date, b_to: date) -> bool:
    """Inclusive range overlap - same semantics as Postgres daterange '[]' &&."""
    return a_from <= b_to and b_from <= a_to
