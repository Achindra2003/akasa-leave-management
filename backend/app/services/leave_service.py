"""Leave application service - the *only* place leave state changes.

Both the REST API and the AI assistant call these functions, so every rule (validation,
routing, RBAC, state machine, audit) applies identically regardless of channel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import clock
from app.domain.enums import Action, Channel, LeaveStatus, Role, StepDecision
from app.domain.errors import Forbidden, NotFound, OverlappingLeave, StaleRequest, ValidationFailed
from app.domain.policy import (
    DEFAULT_POLICY,
    DocumentMeta,
    LeavePolicy,
    requires_escalation,
    validate_documents,
    validate_leave_request,
)
from app.domain.workflow import (
    APPROVER_ACTIONS,
    COMMENT_REQUIRED,
    OrgPerson,
    allowed_actions,
    level_status,
    next_status,
    plan_approval_chain,
)
from app.models import (
    ApprovalStep,
    Attachment,
    BlackoutPeriod,
    Comment,
    Department,
    LeaveRequest,
    User,
)
from app.services import audit
from app.services.notify import notify


@dataclass(frozen=True, slots=True)
class Actor:
    user: User
    channel: Channel = Channel.UI


@dataclass(slots=True)
class Upload:
    filename: str
    content_type: str
    content: bytes

    @property
    def meta(self) -> DocumentMeta:
        return DocumentMeta(self.filename, self.content_type, len(self.content))


@dataclass(slots=True)
class LeaveService:
    session: AsyncSession
    policy: LeavePolicy = field(default_factory=lambda: DEFAULT_POLICY)
    today: date | None = None  # injectable clock for tests

    def _today(self) -> date:
        return self.today or clock.today()

    # ------------------------------------------------------------------ queries
    def _detail_query(self) -> Select[tuple[LeaveRequest]]:
        return select(LeaveRequest).options(
            selectinload(LeaveRequest.employee).selectinload(User.department),
            selectinload(LeaveRequest.steps).selectinload(ApprovalStep.approver),
            selectinload(LeaveRequest.steps).selectinload(ApprovalStep.acted_by),
            selectinload(LeaveRequest.blackout),
            selectinload(LeaveRequest.attachments),
            selectinload(LeaveRequest.comments).selectinload(Comment.author),
        )

    async def get(self, request_id: int, viewer: User) -> LeaveRequest:
        req = await self.session.scalar(self._detail_query().where(LeaveRequest.id == request_id))
        if req is None or not can_view(req, viewer, await self.acting_for(viewer)):
            # Same response for "missing" and "not yours": don't leak existence.
            raise NotFound("We couldn't find that leave request.")
        return req

    async def list_mine(self, user: User) -> list[LeaveRequest]:
        q = (
            self._detail_query()
            .where(LeaveRequest.employee_id == user.id)
            .order_by(LeaveRequest.from_date.desc(), LeaveRequest.id.desc())
        )
        return list((await self.session.scalars(q)).all())

    async def acting_for(self, user: User) -> set[int]:
        """Approvers this user currently stands in for: they named this user as delegate
        AND are on approved leave today (D-020). Computed live - no stale 'OOO' flags."""
        today = self._today()
        q = (
            select(User.id)
            .join(LeaveRequest, LeaveRequest.employee_id == User.id)
            .where(
                User.delegate_id == user.id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.from_date <= today,
                LeaveRequest.to_date >= today,
            )
        )
        return set((await self.session.scalars(q)).all())

    async def pending_for(self, approver: User) -> list[LeaveRequest]:
        """Requests whose *current* step is assigned to this approver, or to someone they
        are covering for while that person is on leave."""
        ids = {approver.id} | await self.acting_for(approver)
        q = (
            self._detail_query()
            .join(ApprovalStep, ApprovalStep.request_id == LeaveRequest.id)
            .where(
                ApprovalStep.approver_id.in_(ids),
                LeaveRequest.employee_id != approver.id,
                ApprovalStep.decision == StepDecision.PENDING,
                ApprovalStep.level == LeaveRequest.current_level,
                LeaveRequest.status.in_([LeaveStatus.PENDING_MANAGER, LeaveStatus.PENDING_HOD]),
            )
            .order_by(LeaveRequest.created_at)
        )
        return list((await self.session.scalars(q)).unique().all())

    async def handled_by(self, approver: User, limit: int = 50) -> list[LeaveRequest]:
        """Requests this approver is/was involved in but are not waiting on them now."""
        q = (
            self._detail_query()
            .join(ApprovalStep, ApprovalStep.request_id == LeaveRequest.id)
            .where(
                ApprovalStep.approver_id == approver.id,
                ApprovalStep.decision != StepDecision.PENDING,
            )
            .order_by(LeaveRequest.updated_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(q)).unique().all())

    async def list_all(self, status: LeaveStatus | None = None) -> list[LeaveRequest]:
        q = self._detail_query().order_by(LeaveRequest.created_at.desc())
        if status:
            q = q.where(LeaveRequest.status == status)
        return list((await self.session.scalars(q)).all())

    async def find_overlaps(
        self, employee_id: int, from_date: date, to_date: date, exclude_id: int | None = None
    ) -> list[LeaveRequest]:
        q = select(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.not_in([LeaveStatus.REJECTED, LeaveStatus.CANCELLED]),
            LeaveRequest.from_date <= to_date,
            LeaveRequest.to_date >= from_date,
        )
        if exclude_id:
            q = q.where(LeaveRequest.id != exclude_id)
        return list((await self.session.scalars(q)).all())

    async def team_overlaps(self, req: LeaveRequest) -> list[LeaveRequest]:
        """Colleagues (same manager or same department) off during the same dates."""
        emp = req.employee
        peers = select(User.id).where(
            User.id != emp.id,
            (User.manager_id == emp.manager_id) | (User.department_id == emp.department_id),
        )
        q = (
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.employee))
            .where(
                LeaveRequest.employee_id.in_(peers),
                LeaveRequest.status.not_in([LeaveStatus.REJECTED, LeaveStatus.CANCELLED]),
                LeaveRequest.from_date <= req.to_date,
                LeaveRequest.to_date >= req.from_date,
            )
        )
        return list((await self.session.scalars(q)).all())

    # ----------------------------------------------------------------- commands
    async def submit(
        self,
        actor: Actor,
        *,
        from_date: date,
        to_date: date,
        reason: str,
        uploads: list[Upload] | None = None,
    ) -> LeaveRequest:
        uploads = uploads or []
        employee = actor.user
        total = validate_leave_request(
            from_date=from_date,
            to_date=to_date,
            reason=reason,
            today=self._today(),
            documents=[u.meta for u in uploads],
            policy=self.policy,
        )

        # Friendly pre-check; the DB exclusion constraint is the real guarantee (races).
        clashes = await self.find_overlaps(employee.id, from_date, to_date)
        if clashes:
            raise _overlap_error(clashes[0])

        blackout = await self.find_blackout(employee, from_date, to_date)
        # Long leave needs documents AND L2; a blackout window needs L2 only (D-019).
        escalate = requires_escalation(total, self.policy) or blackout is not None
        steps = plan_approval_chain(
            await self._org_person(employee),
            escalate=escalate,
            hr_admin_ids=await self._hr_admin_ids(),
        )

        req = LeaveRequest(
            employee_id=employee.id,
            from_date=from_date,
            to_date=to_date,
            total_days=total,
            reason=reason.strip(),
            status=LeaveStatus.PENDING_MANAGER,
            requires_documents=requires_escalation(total, self.policy),
            blackout_id=blackout.id if blackout else None,
            current_level=1,
            channel=actor.channel,
        )
        req.steps = [
            ApprovalStep(level=s.level, approver_id=s.approver_id, approver_role=s.approver_role)
            for s in steps
        ]
        req.attachments = [_attachment(u, employee.id) for u in uploads]
        self.session.add(req)
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            if "no_overlapping_active_leave" in str(e.orig):
                raise OverlappingLeave(
                    "You already have a leave request covering some of these dates."
                ) from e
            raise

        audit.record(
            self.session,
            actor_id=employee.id,
            channel=actor.channel,
            action="leave.submitted",
            entity="leave_request",
            entity_id=req.id,
            after=_snapshot(req),
            meta={
                "approvers": [
                    {"level": s.level, "approverId": s.approver_id, "role": s.approver_role}
                    for s in steps
                ],
                "documents": [u.filename for u in uploads],
            },
        )
        where = f" (blackout: {blackout.name})" if blackout else ""
        await notify(
            self.session,
            steps[0].approver_id,
            "approval_needed",
            f"{employee.name} requested {total} {'day' if total == 1 else 'days'} off",
            f"{from_date:%d %b} - {to_date:%d %b}{where}",
            req.id,
        )
        await self.session.commit()
        return await self.get(req.id, employee)

    async def decide(
        self,
        actor: Actor,
        request_id: int,
        action: Action,
        *,
        comment: str | None = None,
        expected_version: int | None = None,
    ) -> LeaveRequest:
        """Approver actions: APPROVE / REJECT / REQUEST_INFO."""
        if action not in APPROVER_ACTIONS:
            raise ValidationFailed("That isn't an approver action.")
        req = await self._load_for_update(request_id, actor.user, expected_version)
        step = _current_step(req)
        acting = await self.acting_for(actor.user)
        if req.employee_id == actor.user.id:
            raise Forbidden("You can't approve or reject your own leave request.")
        if step is not None and any(
            s.level != step.level
            and actor.user.id in (s.approver_id, s.acted_by_id)
            and s.decision is StepDecision.APPROVED
            for s in req.steps
        ):
            raise Forbidden("You already signed off this request at another level.")
        if step is None or (step.approver_id != actor.user.id and step.approver_id not in acting):
            if req.employee_id == actor.user.id:
                raise Forbidden("You can't approve or reject your own leave request.")
            raise Forbidden("This request isn't waiting on your approval.")
        comment = _require_comment(action, comment)

        before = _snapshot(req)
        has_next = any(s.level == step.level + 1 for s in req.steps)
        new_status = next_status(req.status, action, has_next_level=has_next)
        step.decided_at = datetime.now(UTC)
        # Set the object, not just the id, so the in-session identity map stays correct.
        step.acted_by = actor.user
        step.comment = comment

        if action is Action.APPROVE:
            step.decision = StepDecision.APPROVED
            req.current_level = step.level + 1 if new_status is LeaveStatus.PENDING_HOD else None
        elif action is Action.REJECT:
            step.decision = StepDecision.REJECTED
            req.current_level = None
            _skip_remaining(req, after_level=step.level)
        else:  # REQUEST_INFO - step stays theirs; it re-opens when the employee responds
            step.decision = StepDecision.INFO_REQUESTED
            req.info_requested_level = step.level

        req.status = new_status
        if comment:
            kind = {Action.APPROVE: "APPROVAL", Action.REJECT: "REJECTION"}.get(
                action, "INFO_REQUEST"
            )
            req.comments.append(Comment(author_id=actor.user.id, kind=kind, body=comment))
        audit.record(
            self.session,
            actor_id=actor.user.id,
            channel=actor.channel,
            action=f"leave.{action.value.lower()}",
            entity="leave_request",
            entity_id=req.id,
            before=before,
            after=_snapshot(req),
            meta={"level": step.level, "comment": comment},
        )
        await self._notify_decision(req, action, actor.user, comment)
        await self.session.commit()  # version_id_col -> StaleDataError if someone beat us
        return await self.get(req.id, actor.user)

    async def respond(
        self,
        actor: Actor,
        request_id: int,
        *,
        comment: str | None,
        uploads: list[Upload] | None = None,
        expected_version: int | None = None,
    ) -> LeaveRequest:
        """Employee answers an information request (optionally adding documents)."""
        uploads = uploads or []
        req = await self._load_for_update(request_id, actor.user, expected_version)
        if req.employee_id != actor.user.id:
            raise Forbidden("Only the employee who applied can respond to this request.")
        comment = _require_comment(Action.RESPOND, comment)
        doc_err = validate_documents([u.meta for u in uploads], self.policy)
        if doc_err:
            raise ValidationFailed(doc_err, details={"fields": {"documents": doc_err}})

        before = _snapshot(req)
        level = req.info_requested_level or 1
        req.status = next_status(req.status, Action.RESPOND, info_requested_level=level)
        for s in req.steps:
            if s.level == level:
                s.decision = StepDecision.PENDING
        req.current_level = level
        req.info_requested_level = None
        req.comments.append(Comment(author_id=actor.user.id, kind="INFO_RESPONSE", body=comment))
        for u in uploads:
            req.attachments.append(_attachment(u, actor.user.id))
        audit.record(
            self.session,
            actor_id=actor.user.id,
            channel=actor.channel,
            action="leave.info_provided",
            entity="leave_request",
            entity_id=req.id,
            before=before,
            after=_snapshot(req),
            meta={"comment": comment, "documents": [u.filename for u in uploads]},
        )
        current = next((st for st in req.steps if st.level == level), None)
        if current:
            await notify(
                self.session,
                current.approver_id,
                "info_provided",
                f"{actor.user.name} replied to your question",
                comment,
                req.id,
            )
        await self.session.commit()
        return await self.get(req.id, actor.user)

    async def cancel(
        self, actor: Actor, request_id: int, *, expected_version: int | None = None
    ) -> LeaveRequest:
        req = await self._load_for_update(request_id, actor.user, expected_version)
        if req.employee_id != actor.user.id:
            raise Forbidden("Only the employee who applied can withdraw this request.")
        before = _snapshot(req)
        req.status = next_status(req.status, Action.CANCEL)
        req.current_level = None
        _skip_remaining(req, after_level=0)
        audit.record(
            self.session,
            actor_id=actor.user.id,
            channel=actor.channel,
            action="leave.cancelled",
            entity="leave_request",
            entity_id=req.id,
            before=before,
            after=_snapshot(req),
        )
        await self.session.commit()
        return await self.get(req.id, actor.user)

    async def get_attachment(self, attachment_id: int, viewer: User) -> Attachment:
        att = await self.session.get(Attachment, attachment_id)
        if att is None:
            raise NotFound("We couldn't find that document.")
        await self.get(att.request_id, viewer)  # raises NotFound if viewer lacks access
        await self.session.refresh(att, ["content"])
        audit.record(
            self.session,
            actor_id=viewer.id,
            channel=Channel.UI,
            action="document.viewed",
            entity="attachment",
            entity_id=att.id,
            meta={"requestId": att.request_id, "filename": att.filename},
        )
        await self.session.commit()
        return att

    # ------------------------------------------------------------------ helpers
    async def find_blackout(
        self, employee: User, from_date: date, to_date: date
    ) -> BlackoutPeriod | None:
        q = (
            select(BlackoutPeriod)
            .where(
                BlackoutPeriod.from_date <= to_date,
                BlackoutPeriod.to_date >= from_date,
                (BlackoutPeriod.department_id.is_(None))
                | (BlackoutPeriod.department_id == employee.department_id),
            )
            .order_by(BlackoutPeriod.from_date)
        )
        return (await self.session.scalars(q)).first()

    async def _notify_decision(
        self, req: LeaveRequest, action: Action, by: User, comment: str | None
    ) -> None:
        span = f"{req.from_date:%d %b} - {req.to_date:%d %b}"
        if action is Action.APPROVE and req.status is LeaveStatus.APPROVED:
            await notify(
                self.session,
                req.employee_id,
                "approved",
                f"Leave approved by {by.name}",
                span,
                req.id,
            )
        elif action is Action.APPROVE:
            nxt = next(s for s in req.steps if s.level == req.current_level)
            await notify(
                self.session,
                req.employee_id,
                "progress",
                f"{by.name} approved - now with {nxt.approver.name}",
                span,
                req.id,
            )
            await notify(
                self.session,
                nxt.approver_id,
                "approval_needed",
                f"{req.employee.name}'s leave needs your sign-off",
                span,
                req.id,
            )
        elif action is Action.REJECT:
            await notify(
                self.session,
                req.employee_id,
                "rejected",
                f"Leave rejected by {by.name}",
                comment,
                req.id,
            )
        else:
            await notify(
                self.session,
                req.employee_id,
                "info_requested",
                f"{by.name} needs more information",
                comment,
                req.id,
            )

    async def _load_for_update(
        self, request_id: int, user: User, expected_version: int | None
    ) -> LeaveRequest:
        req = await self.get(request_id, user)
        if expected_version is not None and expected_version != req.version:
            raise StaleRequest(
                "This request changed since you opened it. Refresh to see the latest status."
            )
        return req

    async def _org_person(self, user: User) -> OrgPerson:
        hod_id = None
        if user.department_id:
            hod_id = await self.session.scalar(
                select(Department.hod_id).where(Department.id == user.department_id)
            )
        return OrgPerson(id=user.id, role=user.role, manager_id=user.manager_id, hod_id=hod_id)

    async def _hr_admin_ids(self) -> list[int]:
        q = select(User.id).where(User.role == Role.HR_ADMIN).order_by(User.id)
        return list((await self.session.scalars(q)).all())

    async def stats(self) -> dict[str, object]:
        rows = (
            await self.session.execute(
                select(LeaveRequest.status, func.count()).group_by(LeaveRequest.status)
            )
        ).all()
        by_status = {s.value: 0 for s in LeaveStatus} | {r[0].value: r[1] for r in rows}
        cutoff = datetime.now(UTC) - timedelta(hours=48)
        stale = await self.session.scalar(
            select(func.count()).where(
                LeaveRequest.status.in_([LeaveStatus.PENDING_MANAGER, LeaveStatus.PENDING_HOD]),
                LeaveRequest.updated_at < cutoff,
            )
        )
        via_ai = await self.session.scalar(
            select(func.count()).where(LeaveRequest.channel == Channel.ASSISTANT)
        )
        return {
            "by_status": by_status,
            "total": sum(by_status.values()),
            "pending_over_48h": stale or 0,
            "via_assistant": via_ai or 0,
        }


# ---------------------------------------------------------------- pure helpers
def can_view(req: LeaveRequest, viewer: User, acting_for: set[int] | None = None) -> bool:
    """Privacy rule (D-001): requester, approvers in the chain, and HR only."""
    return (
        viewer.role is Role.HR_ADMIN
        or req.employee_id == viewer.id
        or any(s.approver_id == viewer.id or s.acted_by_id == viewer.id for s in req.steps)
        or any(s.approver_id in (acting_for or set()) for s in req.steps)
    )


def viewer_actions(
    req: LeaveRequest, viewer: User, acting_for: set[int] | None = None
) -> list[Action]:
    """What *this* viewer may do now - the UI renders exactly these buttons."""
    possible = allowed_actions(req.status)
    out: set[Action] = set()
    if req.employee_id == viewer.id:
        out |= possible & {Action.CANCEL, Action.RESPOND}
    step = _current_step(req)
    mine = bool(
        step and (step.approver_id == viewer.id or step.approver_id in (acting_for or set()))
    )
    already = any(
        viewer.id in (s.approver_id, s.acted_by_id) and s.decision is StepDecision.APPROVED
        for s in req.steps
    )
    if mine and not already and req.employee_id != viewer.id:
        out |= possible & APPROVER_ACTIONS
    order = list(Action)
    return sorted(out, key=order.index)


def _current_step(req: LeaveRequest) -> ApprovalStep | None:
    if req.status not in (LeaveStatus.PENDING_MANAGER, LeaveStatus.PENDING_HOD):
        return None
    lvl = 1 if req.status is LeaveStatus.PENDING_MANAGER else 2
    assert level_status(lvl) is req.status
    return next((s for s in req.steps if s.level == lvl), None)


def _skip_remaining(req: LeaveRequest, *, after_level: int) -> None:
    for s in req.steps:
        if s.level > after_level and s.decision in (
            StepDecision.PENDING,
            StepDecision.INFO_REQUESTED,
        ):
            s.decision = StepDecision.SKIPPED


def _require_comment(action: Action, comment: str | None) -> str | None:
    comment = (comment or "").strip() or None
    if action in COMMENT_REQUIRED and not comment:
        msg = {
            Action.REJECT: "Please add a comment explaining why the leave is rejected.",
            Action.REQUEST_INFO: "Please describe what information you need from the employee.",
            Action.RESPOND: "Please add a short note with your response.",
        }[action]
        raise ValidationFailed(msg, details={"fields": {"comment": msg}})
    return comment


def _attachment(u: Upload, uploader_id: int) -> Attachment:
    return Attachment(
        filename=u.filename[:255],
        content_type=u.content_type,
        size=len(u.content),
        content=u.content,
        uploaded_by=uploader_id,
        sha256=hashlib.sha256(u.content).hexdigest(),
    )


def _snapshot(req: LeaveRequest) -> dict[str, object]:
    return {
        "status": req.status.value,
        "fromDate": req.from_date.isoformat(),
        "toDate": req.to_date.isoformat(),
        "totalDays": req.total_days,
        "currentLevel": req.current_level,
    }


def _overlap_error(clash: LeaveRequest) -> OverlappingLeave:
    return OverlappingLeave(
        f"You already have a {clash.status.value.replace('_', ' ').lower()} leave from "
        f"{clash.from_date:%d %b} to {clash.to_date:%d %b %Y} that overlaps these dates.",
        details={"conflictingRequestId": clash.id},
    )
