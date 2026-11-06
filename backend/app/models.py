"""ORM models (SQLAlchemy 2.0 typed declarative)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.domain.enums import Channel, LeaveStatus, Role, StepDecision


def _enum(e: type) -> Enum:
    # VARCHAR + CHECK instead of native PG enums: adding a status later is a trivial migration.
    return Enum(e, native_enum=False, length=32, validate_strings=True)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    hod_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, ondelete="SET NULL")
    )

    hod: Mapped[User | None] = relationship(foreign_keys=[hod_id])


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.EMPLOYEE)
    title: Mapped[str | None] = mapped_column(String(120))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )

    manager: Mapped[User | None] = relationship(remote_side=[id], foreign_keys=[manager_id])
    department: Mapped[Department | None] = relationship(foreign_keys=[department_id])


class LeaveRequest(TimestampMixin, Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("to_date >= from_date", name="date_order"),
        CheckConstraint("total_days > 0", name="positive_days"),
        # The DB itself guarantees no overlapping *active* leave per employee, even under
        # concurrent submissions (RESEARCH.md §2.3). Requires the btree_gist extension.
        ExcludeConstraint(
            ("employee_id", "="),
            (
                func.daterange(
                    literal_column("from_date"), literal_column("to_date"), literal_column("'[]'")
                ),
                "&&",
            ),
            name="no_overlapping_active_leave",
            using="gist",
            where=text("status NOT IN ('REJECTED', 'CANCELLED')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    total_days: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[LeaveStatus] = mapped_column(_enum(LeaveStatus), index=True)
    requires_documents: Mapped[bool] = mapped_column(default=False)
    current_level: Mapped[int | None] = mapped_column(Integer)
    info_requested_level: Mapped[int | None] = mapped_column(Integer)
    channel: Mapped[Channel] = mapped_column(_enum(Channel), default=Channel.UI)
    # Optimistic locking: concurrent approver actions can't both win.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    steps: Mapped[list[ApprovalStep]] = relationship(
        back_populates="request", order_by="ApprovalStep.level", cascade="all, delete-orphan"
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="request", order_by="Attachment.id", cascade="all, delete-orphan"
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="request", order_by="Comment.id", cascade="all, delete-orphan"
    )


class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    __table_args__ = (UniqueConstraint("request_id", "level", name="uq_step_level"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("leave_requests.id", ondelete="CASCADE"))
    level: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    approver_role: Mapped[Role] = mapped_column(_enum(Role))
    decision: Mapped[StepDecision] = mapped_column(
        _enum(StepDecision), default=StepDecision.PENDING
    )
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[LeaveRequest] = relationship(back_populates="steps")
    approver: Mapped[User] = relationship()


class Attachment(TimestampMixin, Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("leave_requests.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)  # D-007
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    request: Mapped[LeaveRequest] = relationship(back_populates="attachments")


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("leave_requests.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))  # APPROVE|REJECT|INFO_REQUEST|INFO_RESPONSE|...
    body: Mapped[str] = mapped_column(Text)

    request: Mapped[LeaveRequest] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class AuditLog(TimestampMixin, Base):
    """Append-only. The application never updates or deletes rows (enforced by a trigger)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[Channel] = mapped_column(_enum(Channel))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(64))

    actor: Mapped[User | None] = relationship()


class AgentRun(TimestampMixin, Base):
    """Trace of every AI run: what it saw, which tools it called, what it produced."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # assistant | copilot
    thread_id: Mapped[str | None] = mapped_column(String(64), index=True)
    input: Mapped[str] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
