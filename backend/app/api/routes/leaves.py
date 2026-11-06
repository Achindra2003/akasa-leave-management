from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, LeaveServiceDep, SessionDep
from app.api.presenters import audit_out, leave_detail, leave_summary
from app.core.config import get_settings
from app.domain.enums import Action
from app.domain.errors import ValidationFailed
from app.models import AuditLog
from app.schemas import AuditOut, DecisionIn, LeaveDetail, LeaveSummary, PolicyOut
from app.services.leave_service import Actor, Upload

router = APIRouter(tags=["leaves"])

_CHUNK = 64 * 1024


async def read_uploads(files: list[UploadFile] | None) -> list[Upload]:
    """Read uploads with a hard size cap (never trust Content-Length)."""
    limit = get_settings().policy.max_document_bytes
    out: list[Upload] = []
    for f in files or []:
        if not f.filename:
            continue
        buf = bytearray()
        while chunk := await f.read(_CHUNK):
            buf += chunk
            if len(buf) > limit:
                mb = limit // (1024 * 1024)
                msg = f"'{f.filename}' is larger than {mb} MB."
                raise ValidationFailed(msg, details={"fields": {"documents": msg}})
        out.append(Upload(f.filename, f.content_type or "application/octet-stream", bytes(buf)))
    return out


@router.get("/policy", response_model=PolicyOut)
async def policy() -> PolicyOut:
    """Policy is exposed so the UI mirrors server rules instead of hard-coding them."""
    p = get_settings().policy
    return PolicyOut(
        escalation_threshold_days=p.escalation_threshold_days,
        max_span_days=p.max_span_days,
        max_upload_mb=p.max_document_bytes // (1024 * 1024),
        allowed_document_types=sorted(p.allowed_document_types),
    )


@router.post("/leaves", response_model=LeaveDetail, status_code=status.HTTP_201_CREATED)
async def apply_for_leave(
    user: CurrentUser,
    svc: LeaveServiceDep,
    from_date: Annotated[date, Form(alias="fromDate")],
    to_date: Annotated[date, Form(alias="toDate")],
    reason: Annotated[str, Form(max_length=500)],
    documents: Annotated[list[UploadFile] | None, File()] = None,
) -> LeaveDetail:
    """Submit a leave request (multipart, so documents travel in the same transaction).

    The employee is always the signed-in user; ``employeeName`` from the brief's payload is
    returned in the response rather than trusted from the client.
    """
    req = await svc.submit(
        Actor(user),
        from_date=from_date,
        to_date=to_date,
        reason=reason,
        uploads=await read_uploads(documents),
    )
    return leave_detail(req, user)


@router.get("/leaves/mine", response_model=list[LeaveSummary])
async def my_leaves(user: CurrentUser, svc: LeaveServiceDep) -> list[LeaveSummary]:
    return [leave_summary(r) for r in await svc.list_mine(user)]


@router.get("/leaves/{request_id}", response_model=LeaveDetail)
async def get_leave(request_id: int, user: CurrentUser, svc: LeaveServiceDep) -> LeaveDetail:
    return leave_detail(await svc.get(request_id, user), user)


@router.get("/leaves/{request_id}/timeline", response_model=list[AuditOut])
async def leave_timeline(
    request_id: int, user: CurrentUser, svc: LeaveServiceDep, session: SessionDep
) -> list[AuditOut]:
    """Audit trail of one request, visible to anyone allowed to view the request."""
    await svc.get(request_id, user)
    q = (
        select(AuditLog)
        .options(selectinload(AuditLog.actor))
        .where(AuditLog.entity == "leave_request", AuditLog.entity_id == request_id)
        .order_by(AuditLog.id)
    )
    return [audit_out(a) for a in (await session.scalars(q)).all()]


@router.post("/leaves/{request_id}/cancel", response_model=LeaveDetail)
async def cancel_leave(
    request_id: int, user: CurrentUser, svc: LeaveServiceDep, body: DecisionIn | None = None
) -> LeaveDetail:
    req = await svc.cancel(Actor(user), request_id, expected_version=body.version if body else None)
    return leave_detail(req, user)


@router.post("/leaves/{request_id}/respond", response_model=LeaveDetail)
async def respond_to_info_request(
    request_id: int,
    user: CurrentUser,
    svc: LeaveServiceDep,
    comment: Annotated[str, Form(max_length=1000)],
    version: Annotated[int | None, Form()] = None,
    documents: Annotated[list[UploadFile] | None, File()] = None,
) -> LeaveDetail:
    req = await svc.respond(
        Actor(user),
        request_id,
        comment=comment,
        uploads=await read_uploads(documents),
        expected_version=version,
    )
    return leave_detail(req, user)


# ---- approver actions ------------------------------------------------------
@router.get("/approvals/pending", response_model=list[LeaveSummary], tags=["approvals"])
async def pending_approvals(user: CurrentUser, svc: LeaveServiceDep) -> list[LeaveSummary]:
    return [leave_summary(r) for r in await svc.pending_for(user)]


@router.get("/approvals/history", response_model=list[LeaveSummary], tags=["approvals"])
async def approval_history(user: CurrentUser, svc: LeaveServiceDep) -> list[LeaveSummary]:
    return [leave_summary(r) for r in await svc.handled_by(user)]


def _decision_route(action: Action):  # type: ignore[no-untyped-def]
    async def handler(
        request_id: int, body: DecisionIn, user: CurrentUser, svc: LeaveServiceDep
    ) -> LeaveDetail:
        req = await svc.decide(
            Actor(user), request_id, action, comment=body.comment, expected_version=body.version
        )
        return leave_detail(req, user)

    return handler


for _path, _action, _summary in [
    ("approve", Action.APPROVE, "Approve (comment optional)"),
    ("reject", Action.REJECT, "Reject (comment required)"),
    ("request-info", Action.REQUEST_INFO, "Ask the employee for more information"),
]:
    router.add_api_route(
        f"/approvals/{{request_id}}/{_path}",
        _decision_route(_action),
        methods=["POST"],
        response_model=LeaveDetail,
        tags=["approvals"],
        summary=_summary,
        name=f"approval_{_path}",
    )


@router.get("/attachments/{attachment_id}", tags=["leaves"])
async def download_attachment(
    attachment_id: int, user: CurrentUser, svc: LeaveServiceDep, download: bool = False
) -> Response:
    att = await svc.get_attachment(attachment_id, user)
    disposition = "attachment" if download else "inline"
    return Response(
        content=att.content,
        media_type=att.content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(att.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
