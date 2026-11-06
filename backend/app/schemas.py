"""API contracts (Pydantic v2). camelCase on the wire to match the brief's payload
(``employeeName``, ``fromDate``...), snake_case in Python. These models are the single
source of truth: the frontend's TypeScript types are generated from the OpenAPI spec."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

from app.domain.enums import Action, Channel, LeaveStatus, Role, StepDecision


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# ---- auth -------------------------------------------------------------------
class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(ApiModel):
    id: int
    name: str
    email: str
    role: Role
    title: str | None = None
    department: str | None = None
    manager_name: str | None = None
    is_approver: bool = False


class TokenOut(ApiModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DemoAccount(ApiModel):
    name: str
    email: str
    role: Role
    title: str | None
    password: str
    blurb: str


# ---- leave ------------------------------------------------------------------
class LeaveCreate(ApiModel):
    """JSON form of a submission (used by the AI assistant). The HTTP endpoint accepts the
    same fields as multipart so documents can be attached in one request."""

    from_date: date
    to_date: date
    reason: str = Field(max_length=500)


class StepOut(ApiModel):
    level: int
    approver_id: int
    approver_name: str
    approver_role: Role
    decision: StepDecision
    comment: str | None
    decided_at: datetime | None


class AttachmentOut(ApiModel):
    id: int
    filename: str
    content_type: str
    size: int
    created_at: datetime


class CommentOut(ApiModel):
    id: int
    author_name: str
    author_role: Role
    kind: str
    body: str
    created_at: datetime


class LeaveSummary(ApiModel):
    id: int
    employee_id: int
    employee_name: str
    department: str | None
    from_date: date
    to_date: date
    total_days: int
    working_days: int
    reason: str
    status: LeaveStatus
    requires_documents: bool
    current_level: int | None
    channel: Channel
    version: int
    created_at: datetime
    updated_at: datetime
    attachment_count: int = 0


class LeaveDetail(LeaveSummary):
    steps: list[StepOut]
    attachments: list[AttachmentOut]
    comments: list[CommentOut]
    allowed_actions: list[Action] = Field(
        description="Actions the *current viewer* may perform - the UI renders only these."
    )


class DecisionIn(ApiModel):
    comment: str | None = Field(default=None, max_length=1000)
    version: int | None = Field(
        default=None, description="Version the approver was looking at (optimistic lock)."
    )


class PolicyOut(ApiModel):
    escalation_threshold_days: int
    max_span_days: int
    max_upload_mb: int
    allowed_document_types: list[str]


class AuditOut(ApiModel):
    id: int
    actor_name: str | None
    channel: Channel
    action: str
    entity: str
    entity_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    meta: dict[str, Any] | None
    correlation_id: str | None
    created_at: datetime


class StatsOut(ApiModel):
    by_status: dict[str, int]
    total: int
    pending_over_48h: int
    via_assistant: int


T = TypeVar("T")


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
