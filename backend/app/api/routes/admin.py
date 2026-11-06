from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import HRUser, LeaveServiceDep, SessionDep
from app.api.presenters import audit_out, leave_summary
from app.domain.enums import LeaveStatus
from app.models import AuditLog
from app.schemas import AuditOut, LeaveSummary, StatsOut

router = APIRouter(prefix="/admin", tags=["hr-admin"])


@router.get("/requests", response_model=list[LeaveSummary])
async def all_requests(
    _: HRUser, svc: LeaveServiceDep, status: LeaveStatus | None = None
) -> list[LeaveSummary]:
    return [leave_summary(r) for r in await svc.list_all(status)]


@router.get("/stats", response_model=StatsOut)
async def stats(_: HRUser, svc: LeaveServiceDep) -> StatsOut:
    return StatsOut(**await svc.stats())  # type: ignore[arg-type]


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    _: HRUser,
    session: SessionDep,
    action: str | None = None,
    limit: int = Query(default=200, le=1000),
) -> list[AuditOut]:
    """Organisation-wide, append-only audit trail (HR only)."""
    q = select(AuditLog).options(selectinload(AuditLog.actor)).order_by(AuditLog.id.desc())
    if action:
        q = q.where(AuditLog.action.startswith(action))
    rows = (await session.scalars(q.limit(limit))).all()
    return [audit_out(a) for a in rows]
