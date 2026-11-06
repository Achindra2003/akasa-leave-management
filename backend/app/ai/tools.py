"""Tools the employee assistant may call.

Security model (D-009/D-012): **least privilege**. Every tool here is read-only or produces a
*draft*. There is deliberately no submit/approve/reject tool - submission happens only in
the graph's ``submit`` node after a human resumes the interrupt, and it goes through the
same ``LeaveService`` (validation, RBAC, audit) as the REST API.

Each tool runs as the signed-in user: ``user_id`` comes from the graph config set by the
server, never from model-generated arguments.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy.orm import selectinload

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.domain.errors import DocumentsRequired, DomainError
from app.domain.policy import requires_escalation, validate_leave_request, working_days
from app.domain.workflow import plan_approval_chain
from app.models import User
from app.services.leave_service import LeaveService


async def _user(svc: LeaveService, config: RunnableConfig) -> User:
    uid = int(config["configurable"]["user_id"])
    user = await svc.session.get(User, uid, options=[selectinload(User.department)])
    if user is None:
        raise DomainError("Unknown user.")
    return user


def _today(config: RunnableConfig) -> date:
    raw = config["configurable"].get("today")
    return datetime.fromisoformat(raw).date() if raw else clock.today()


def _out(data: dict[str, Any]) -> str:
    return json.dumps(data, default=str)


@tool
async def get_leave_policy(config: RunnableConfig) -> str:
    """Get the organisation's leave rules (document threshold, max span, file limits)."""
    p = get_settings().policy
    return _out(
        {
            "escalationThresholdDays": p.escalation_threshold_days,
            "maxSpanDays": p.max_span_days,
            "rule": f"More than {p.escalation_threshold_days} consecutive calendar days requires a "
            "supporting document and approval by Manager then HOD.",
        }
    )


@tool
async def list_my_requests(config: RunnableConfig) -> str:
    """List the current user's leave requests (most recent first) with their status."""
    async with get_sessionmaker()() as s:
        svc = LeaveService(s)
        user = await _user(svc, config)
        reqs = await svc.list_mine(user)
        return _out(
            {
                "requests": [
                    {
                        "id": r.id,
                        "fromDate": r.from_date,
                        "toDate": r.to_date,
                        "totalDays": r.total_days,
                        "status": r.status.value,
                        "currentLevel": r.current_level,
                        # Untrusted user text, returned as data only.
                        "reason": r.reason,
                    }
                    for r in reqs[:10]
                ]
            }
        )


class DraftArgs(BaseModel):
    from_date: str = Field(description="Start date, ISO format YYYY-MM-DD")
    to_date: str = Field(description="End date (inclusive), ISO format YYYY-MM-DD")
    reason: str = Field(description="Short reason for the leave, in the user's words")


@tool(args_schema=DraftArgs)
async def draft_leave_request(
    from_date: str, to_date: str, reason: str, config: RunnableConfig
) -> str:
    """Validate and prepare a leave request DRAFT for the user to review.

    This does NOT submit anything - the user must confirm the draft in the UI. Call it once
    you know the exact dates and a reason.
    """
    try:
        f, t = date.fromisoformat(from_date), date.fromisoformat(to_date)
    except ValueError:
        return _out({"ok": False, "message": "Dates must be in YYYY-MM-DD format."})

    policy = get_settings().policy
    async with get_sessionmaker()() as s:
        svc = LeaveService(s, policy=policy)
        user = await _user(svc, config)
        needs_docs = False
        try:
            total = validate_leave_request(
                from_date=f, to_date=t, reason=reason, today=_today(config), policy=policy
            )
        except DocumentsRequired as e:
            needs_docs, total = True, int(e.details["totalDays"])
        except DomainError as e:
            fields = e.details.get("fields", {})
            return _out({"ok": False, "message": " ".join(fields.values()) or e.message})

        clashes = await svc.find_overlaps(user.id, f, t)
        if clashes:
            c = clashes[0]
            return _out(
                {
                    "ok": False,
                    "message": (
                        f"You already have request #{c.id} ({c.from_date} to {c.to_date}, "
                        f"{c.status.value}) overlapping these dates."
                    ),
                }
            )

        try:
            chain = plan_approval_chain(
                await svc._org_person(user),
                escalate=requires_escalation(total, policy),
                hr_admin_ids=await svc._hr_admin_ids(),
            )
        except DomainError as e:
            return _out({"ok": False, "message": e.message})
        approvers = []
        for step in chain:
            approver = await s.get(User, step.approver_id)
            approvers.append(
                {
                    "level": step.level,
                    "name": approver.name if approver else "?",
                    "role": step.approver_role.value,
                }
            )

    return _out(
        {
            "ok": True,
            "draft": {
                "fromDate": f.isoformat(),
                "toDate": t.isoformat(),
                "reason": reason.strip(),
                "totalDays": total,
                "workingDays": working_days(f, t),
                "requiresDocuments": needs_docs,
                "approvers": approvers,
            },
            "message": (
                "Draft ready. This needs a supporting document, so the user must attach one in the "
                "form before submitting."
                if needs_docs
                else "Draft ready for the user to confirm."
            ),
        }
    )


ASSISTANT_TOOLS = [get_leave_policy, list_my_requests, draft_leave_request]
