"""ORM -> API schema mapping (keeps routers and services free of presentation logic)."""

from app.domain.policy import working_days
from app.models import AuditLog, LeaveRequest, User
from app.schemas import (
    AttachmentOut,
    AuditOut,
    CommentOut,
    LeaveDetail,
    LeaveSummary,
    StepOut,
    UserOut,
)
from app.services.leave_service import viewer_actions


def user_out(u: User, *, is_approver: bool = False) -> UserOut:
    return UserOut(
        id=u.id,
        name=u.name,
        email=u.email,
        role=u.role,
        title=u.title,
        department=u.department.name if u.department else None,
        manager_name=u.manager.name if u.manager else None,
        delegate_id=u.delegate_id,
        delegate_name=u.delegate.name if u.delegate else None,
        is_approver=is_approver,
    )


def leave_summary(r: LeaveRequest) -> LeaveSummary:
    return LeaveSummary(
        id=r.id,
        employee_id=r.employee_id,
        employee_name=r.employee.name,
        department=r.employee.department.name if r.employee.department else None,
        from_date=r.from_date,
        to_date=r.to_date,
        total_days=r.total_days,
        working_days=working_days(r.from_date, r.to_date),
        reason=r.reason,
        status=r.status,
        requires_documents=r.requires_documents,
        current_level=r.current_level,
        channel=r.channel,
        version=r.version,
        created_at=r.created_at,
        updated_at=r.updated_at,
        attachment_count=len(r.attachments),
        blackout_name=r.blackout.name if r.blackout else None,
        flagged_documents=sum(a.verification == "FLAGGED" for a in r.attachments),
    )


def leave_detail(r: LeaveRequest, viewer: User, acting_for: set[int] | None = None) -> LeaveDetail:
    return LeaveDetail(
        **leave_summary(r).model_dump(),
        steps=[
            StepOut(
                level=s.level,
                approver_id=s.approver_id,
                approver_name=s.approver.name,
                approver_role=s.approver_role,
                decision=s.decision,
                comment=s.comment,
                decided_at=s.decided_at,
                acted_by_name=s.acted_by.name
                if s.acted_by and s.acted_by_id != s.approver_id
                else None,
            )
            for s in r.steps
        ],
        attachments=[
            AttachmentOut(
                id=a.id,
                filename=a.filename,
                content_type=a.content_type,
                size=a.size,
                created_at=a.created_at,
                verification=a.verification,
                verification_note=a.verification_note,
                ai_check=a.ai_check,
            )
            for a in r.attachments
        ],
        comments=[
            CommentOut(
                id=c.id,
                author_name=c.author.name,
                author_role=c.author.role,
                kind=c.kind,
                body=c.body,
                created_at=c.created_at,
            )
            for c in r.comments
        ],
        allowed_actions=viewer_actions(r, viewer, acting_for),
    )


def audit_out(a: AuditLog) -> AuditOut:
    return AuditOut(
        id=a.id,
        actor_name=a.actor.name if a.actor else None,
        channel=a.channel,
        action=a.action,
        entity=a.entity,
        entity_id=a.entity_id,
        before=a.before,
        after=a.after,
        meta=a.meta,
        correlation_id=a.correlation_id,
        created_at=a.created_at,
    )
