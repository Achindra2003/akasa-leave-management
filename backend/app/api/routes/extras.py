"""Operational extras: coverage, document verification, blackouts, notifications, delegation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.ai.doc_check import analyse
from app.ai.runtime import ai_runtime
from app.api.deps import CurrentUser, HRUser, LeaveServiceDep, SessionDep
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.logging import log
from app.domain.enums import Channel, Role
from app.domain.errors import Forbidden, NotFound, ValidationFailed
from app.models import Attachment, BlackoutPeriod, LeaveRequest, Notification, User
from app.schemas import ApiModel
from app.services import audit
from app.services.coverage import coverage, suggest_dates, team_members
from app.services.leave_service import LeaveService
from app.services.notify import notify

router = APIRouter(tags=["operations"])


# --------------------------------------------------------------------------- coverage
@router.get("/coverage")
async def coverage_for_dates(
    user: CurrentUser,
    session: SessionDep,
    svc: LeaveServiceDep,
    from_date: date = Query(alias="fromDate"),
    to_date: date = Query(alias="toDate"),
    request_id: int | None = Query(default=None, alias="requestId"),
) -> dict[str, Any]:
    """Team availability for a date range.

    Without ``requestId``: the caller's own team, *as if* they took these days (apply form).
    With ``requestId``: the requester's team, for an approver reviewing it.
    """
    if (to_date - from_date).days > 62 or to_date < from_date:
        raise ValidationFailed("Pick a range of up to two months.")
    ratio = get_settings().min_team_available_ratio
    if request_id is not None:
        req = await svc.get(request_id, user)
        subject = req.employee
        hypothetical = None
    else:
        subject, hypothetical = user, (user.id, from_date, to_date)
    members = await team_members(session, manager_id=subject.manager_id)
    pad = timedelta(days=3)
    cov = await coverage(
        session,
        members=members,
        start=from_date - pad,
        end=to_date + pad,
        min_available_ratio=ratio,
        hypothetical=hypothetical,
    )
    in_range = [d for d in cov["days"] if from_date.isoformat() <= d["date"] <= to_date.isoformat()]  # type: ignore[union-attr]
    short = [d["date"] for d in in_range if d["short"]]
    suggestions = []
    if short:
        suggestions = await suggest_dates(
            session,
            members=members,
            user_id=subject.id,
            from_date=from_date,
            to_date=to_date,
            min_available_ratio=ratio,
            today=clock.today(),
        )
    blackout = await svc.find_blackout(subject, from_date, to_date)
    return {
        **cov,
        "range": {"from": from_date, "to": to_date},
        "shortDays": short,
        "suggestions": suggestions,
        "blackout": {
            "name": blackout.name,
            "reason": blackout.reason,
            "fromDate": blackout.from_date,
            "toDate": blackout.to_date,
        }
        if blackout
        else None,
    }


@router.get("/coverage/team")
async def team_calendar(
    user: CurrentUser,
    session: SessionDep,
    start: date | None = None,
    days: int = Query(default=28, ge=7, le=62),
    manager_id: int | None = Query(default=None, alias="managerId"),
) -> dict[str, Any]:
    """Roster view for a manager's direct reports (HR may view any manager's team)."""
    mid = manager_id if (manager_id and user.role is Role.HR_ADMIN) else user.id
    members = await team_members(session, manager_id=mid)
    start = start or clock.today()
    cov = await coverage(
        session,
        members=members,
        start=start,
        end=start + timedelta(days=days - 1),
        min_available_ratio=get_settings().min_team_available_ratio,
    )
    blackouts = (
        await session.scalars(
            select(BlackoutPeriod).where(
                BlackoutPeriod.to_date >= start,
                BlackoutPeriod.from_date <= start + timedelta(days=days),
            )
        )
    ).all()
    return {
        **cov,
        "members": [{"id": m.id, "name": m.name, "title": m.title} for m in members],
        "blackouts": [
            {"name": b.name, "fromDate": b.from_date, "toDate": b.to_date} for b in blackouts
        ],
    }


# ------------------------------------------------------------- document verification
async def _attachment_for_reviewer(
    svc: LeaveService, user: User, attachment_id: int
) -> tuple[Attachment, LeaveRequest]:
    att = await svc.session.get(Attachment, attachment_id)
    if att is None:
        raise NotFound("We couldn't find that document.")
    req = await svc.get(att.request_id, user)
    acting = await svc.acting_for(user)
    reviewer = user.role is Role.HR_ADMIN or any(
        s.approver_id == user.id or s.approver_id in acting or s.acted_by_id == user.id
        for s in req.steps
    )
    if not reviewer or req.employee_id == user.id:
        raise Forbidden("Only approvers and HR can verify documents.")
    return att, req


async def run_document_checks(request_id: int) -> None:
    """Background task after upload: pre-check every unchecked document of a request."""
    try:
        async with get_sessionmaker()() as session:
            req = await session.scalar(
                select(LeaveRequest)
                .options(selectinload(LeaveRequest.employee))
                .where(LeaveRequest.id == request_id)
            )
            atts = (
                await session.scalars(
                    select(Attachment).where(
                        Attachment.request_id == request_id, Attachment.ai_check.is_(None)
                    )
                )
            ).all()
            for att in atts:
                await session.refresh(att, ["content"])
                att.ai_check = await analyse(session, att, req, model=_model(), live=_live())  # type: ignore[arg-type]
            await session.commit()
    except Exception as e:  # never let a pre-check failure affect the request
        log.warning("document_check_failed", request_id=request_id, error=repr(e))


def _model():  # type: ignore[no-untyped-def]
    return ai_runtime.copilot and ai_runtime.model


def _live() -> bool:
    return bool(ai_runtime.info and ai_runtime.info.live)


@router.post("/attachments/{attachment_id}/check")
async def check_document(
    attachment_id: int, user: CurrentUser, svc: LeaveServiceDep, session: SessionDep
) -> dict[str, Any]:
    att, req = await _attachment_for_reviewer(svc, user, attachment_id)
    await session.refresh(att, ["content"])
    att.ai_check = await analyse(session, att, req, model=_model(), live=_live())
    await session.commit()
    return att.ai_check


class VerifyIn(ApiModel):
    decision: Literal["VERIFIED", "FLAGGED"]
    note: str | None = Field(default=None, max_length=500)


@router.post("/attachments/{attachment_id}/verify")
async def verify_document(
    attachment_id: int, body: VerifyIn, user: CurrentUser, svc: LeaveServiceDep, session: SessionDep
) -> dict[str, Any]:
    att, req = await _attachment_for_reviewer(svc, user, attachment_id)
    if body.decision == "FLAGGED" and not (body.note or "").strip():
        raise ValidationFailed(
            "Please say what's wrong with the document.",
            details={"fields": {"note": "Required when flagging."}},
        )
    before = {"verification": att.verification}
    att.verification, att.verification_note = body.decision, (body.note or "").strip() or None
    att.verified_by, att.verified_at = user.id, datetime.now(UTC)
    audit.record(
        session,
        actor_id=user.id,
        channel=Channel.UI,
        action=f"document.{body.decision.lower()}",
        entity="attachment",
        entity_id=att.id,
        before=before,
        after={"verification": att.verification},
        meta={"requestId": req.id, "filename": att.filename, "note": body.note},
    )
    if body.decision == "FLAGGED":
        await notify(
            session,
            req.employee_id,
            "document_flagged",
            f"{user.name} flagged '{att.filename}'",
            body.note,
            req.id,
        )
    await session.commit()
    return {"id": att.id, "verification": att.verification, "note": att.verification_note}


# ------------------------------------------------------------------------ blackouts
class BlackoutIn(ApiModel):
    name: str = Field(min_length=3, max_length=120)
    reason: str | None = Field(default=None, max_length=500)
    from_date: date
    to_date: date
    department_id: int | None = None


def _blackout_out(b: BlackoutPeriod) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "reason": b.reason,
        "fromDate": b.from_date,
        "toDate": b.to_date,
        "departmentId": b.department_id,
        "department": b.department.name if b.department else None,
    }


@router.get("/blackouts")
async def list_blackouts(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    q = (
        select(BlackoutPeriod)
        .options(selectinload(BlackoutPeriod.department))
        .where(BlackoutPeriod.to_date >= clock.today())
        .order_by(BlackoutPeriod.from_date)
    )
    if user.role is not Role.HR_ADMIN:
        q = q.where(
            (BlackoutPeriod.department_id.is_(None))
            | (BlackoutPeriod.department_id == user.department_id)
        )
    return [_blackout_out(b) for b in (await session.scalars(q)).all()]


@router.post("/admin/blackouts", status_code=201)
async def create_blackout(body: BlackoutIn, user: HRUser, session: SessionDep) -> dict[str, Any]:
    if body.to_date < body.from_date:
        raise ValidationFailed(
            "End date can't be before the start date.",
            details={"fields": {"toDate": "Must be on/after the start."}},
        )
    b = BlackoutPeriod(
        name=body.name.strip(),
        reason=body.reason,
        from_date=body.from_date,
        to_date=body.to_date,
        department_id=body.department_id,
        created_by=user.id,
    )
    session.add(b)
    await session.flush()
    audit.record(
        session,
        actor_id=user.id,
        channel=Channel.UI,
        action="blackout.created",
        entity="blackout",
        entity_id=b.id,
        after={
            "name": b.name,
            "fromDate": str(b.from_date),
            "toDate": str(b.to_date),
            "departmentId": b.department_id,
        },
    )
    await session.commit()
    await session.refresh(b, ["department"])
    return _blackout_out(b)


@router.delete("/admin/blackouts/{blackout_id}", status_code=204)
async def delete_blackout(blackout_id: int, user: HRUser, session: SessionDep) -> None:
    b = await session.get(BlackoutPeriod, blackout_id)
    if b is None:
        raise NotFound("That blackout period doesn't exist.")
    audit.record(
        session,
        actor_id=user.id,
        channel=Channel.UI,
        action="blackout.deleted",
        entity="blackout",
        entity_id=b.id,
        before={"name": b.name},
    )
    await session.delete(b)
    await session.commit()


# -------------------------------------------------------------------- notifications
@router.get("/notifications")
async def notifications(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    rows = (
        await session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.id.desc())
            .limit(30)
        )
    ).all()
    unread = await session.scalar(
        select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return {
        "unread": unread or 0,
        "items": [
            {
                "id": n.id,
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "requestId": n.request_id,
                "read": n.read_at is not None,
                "createdAt": n.created_at,
            }
            for n in rows
        ],
    }


@router.post("/notifications/read-all", status_code=204)
async def read_all(user: CurrentUser, session: SessionDep) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()


# ----------------------------------------------------------------------- delegation
class DelegateIn(ApiModel):
    delegate_id: int | None


@router.get("/users/delegate-candidates")
async def delegate_candidates(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    q = (
        select(User)
        .where(User.id != user.id, User.role.in_([Role.MANAGER, Role.HOD, Role.HR_ADMIN]))
        .order_by(User.name)
    )
    return [
        {"id": u.id, "name": u.name, "title": u.title, "role": u.role}
        for u in (await session.scalars(q)).all()
    ]


@router.put("/auth/me/delegate")
async def set_delegate(body: DelegateIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    if body.delegate_id == user.id:
        raise ValidationFailed("You can't delegate to yourself.")
    delegate = await session.get(User, body.delegate_id) if body.delegate_id else None
    if body.delegate_id and delegate is None:
        raise NotFound("That person doesn't exist.")
    before = {"delegateId": user.delegate_id}
    user.delegate_id = body.delegate_id
    audit.record(
        session,
        actor_id=user.id,
        channel=Channel.UI,
        action="user.delegate_set",
        entity="user",
        entity_id=user.id,
        before=before,
        after={"delegateId": body.delegate_id},
    )
    await session.commit()
    return {"delegateId": user.delegate_id, "delegateName": delegate.name if delegate else None}
