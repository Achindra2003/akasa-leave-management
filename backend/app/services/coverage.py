"""Team coverage: who is off on each day, and whether staffing stays above the minimum.

"Team" = everyone reporting to the same manager (D-021). At an airline that is the unit a
roster is built around - a line maintenance shift, a crew base. Peers see *who* and *when*,
never *why* (privacy rule, D-001).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import LeaveStatus
from app.models import LeaveRequest, User

ACTIVE = [
    LeaveStatus.PENDING_MANAGER,
    LeaveStatus.PENDING_HOD,
    LeaveStatus.INFO_REQUESTED,
    LeaveStatus.APPROVED,
]


@dataclass(frozen=True, slots=True)
class DayOff:
    user_id: int
    name: str
    tentative: bool  # pending, not yet approved


async def team_members(session: AsyncSession, *, manager_id: int | None) -> list[User]:
    if manager_id is None:
        return []
    q = select(User).where(User.manager_id == manager_id).order_by(User.name)
    return list((await session.scalars(q)).all())


async def coverage(
    session: AsyncSession,
    *,
    members: list[User],
    start: date,
    end: date,
    min_available_ratio: float,
    exclude_request_id: int | None = None,
    hypothetical: tuple[int, date, date] | None = None,
) -> dict[str, object]:
    """Per-day availability for ``members`` between ``start`` and ``end`` (inclusive).

    ``hypothetical`` = (user_id, from, to) adds a not-yet-submitted leave so the apply form
    can show "what happens if I take these days".
    """
    ids = [m.id for m in members]
    names = {m.id: m.name for m in members}
    q = (
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.employee))
        .where(
            LeaveRequest.employee_id.in_(ids),
            LeaveRequest.status.in_(ACTIVE),
            LeaveRequest.from_date <= end,
            LeaveRequest.to_date >= start,
        )
    )
    if exclude_request_id:
        q = q.where(LeaveRequest.id != exclude_request_id)
    leaves = list((await session.scalars(q)).all())

    size = len(members)
    min_available = max(1, math.ceil(size * min_available_ratio)) if size else 0
    days = []
    d = start
    while d <= end:
        off = [
            DayOff(r.employee_id, names.get(r.employee_id, "?"), r.status != LeaveStatus.APPROVED)
            for r in leaves
            if r.from_date <= d <= r.to_date
        ]
        if hypothetical and hypothetical[1] <= d <= hypothetical[2]:
            off.append(DayOff(hypothetical[0], names.get(hypothetical[0], "You"), True))
        available = size - len({o.user_id for o in off})
        days.append(
            {
                "date": d.isoformat(),
                "weekday": d.weekday(),
                "off": [
                    {"userId": o.user_id, "name": o.name, "tentative": o.tentative} for o in off
                ],
                "available": available,
                "short": size > 0 and available < min_available,
            }
        )
        d += timedelta(days=1)
    return {"teamSize": size, "minAvailable": min_available, "days": days}


async def suggest_dates(
    session: AsyncSession,
    *,
    members: list[User],
    user_id: int,
    from_date: date,
    to_date: date,
    min_available_ratio: float,
    today: date,
    search_days: int = 21,
) -> list[dict[str, str]]:
    """Nearest windows of the same length (before or after) with no staffing shortfall."""
    length = (to_date - from_date).days
    lo = max(today, from_date - timedelta(days=search_days))
    hi = to_date + timedelta(days=search_days)
    cov = await coverage(
        session,
        members=members,
        start=lo,
        end=hi + timedelta(days=length),
        min_available_ratio=min_available_ratio,
    )
    by_day = {d["date"]: d for d in cov["days"]}  # type: ignore[index, union-attr]

    def ok(start: date) -> bool:
        for i in range(length + 1):
            day = by_day.get((start + timedelta(days=i)).isoformat())
            if day is None:
                return False
            mine = any(o["userId"] == user_id for o in day["off"])
            available = day["available"] - (0 if mine else 1)
            if available < cov["minAvailable"]:  # type: ignore[operator]
                return False
        return True

    out: list[dict[str, str]] = []
    for delta in range(1, search_days + 1):
        for sign in (1, -1):
            s = from_date + timedelta(days=sign * delta)
            if s < today or s < lo:
                continue
            if ok(s):
                out.append(
                    {"fromDate": s.isoformat(), "toDate": (s + timedelta(days=length)).isoformat()}
                )
            if len(out) == 2:
                return out
    return out
