"""End-to-end API behaviour against real Postgres."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from tests.conftest import PASSWORD, Org

pytestmark = pytest.mark.integration

PDF = ("cert.pdf", b"%PDF-1.4 test", "application/pdf")


def d(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


async def apply(
    client: httpx.AsyncClient,
    org: Org,
    who: str,
    start: int,
    end: int,
    reason: str = "Family function",
    files: list[tuple[str, bytes, str]] | None = None,
) -> httpx.Response:
    return await client.post(
        "/leaves",
        headers=org.h(who),
        data={"fromDate": d(start), "toDate": d(end), "reason": reason},
        files=[("documents", f) for f in (files or [])],
    )


async def act(
    client: httpx.AsyncClient,
    org: Org,
    who: str,
    rid: int,
    action: str,
    comment: str | None = None,
    version: int | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"comment": comment}
    if version is not None:
        body["version"] = version
    return await client.post(f"/approvals/{rid}/{action}", headers=org.h(who), json=body)


# ---------------------------------------------------------------- auth
async def test_login_and_me(client: httpx.AsyncClient, org: Org) -> None:
    r = await client.post("/auth/login", json={"email": "emp@t.demo", "password": PASSWORD})
    assert r.status_code == 200
    token = r.json()["accessToken"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["name"] == "Emp" and me.json()["managerName"] == "Mgr"


async def test_bad_login_is_friendly_problem_json(client: httpx.AsyncClient, org: Org) -> None:
    r = await client.post("/auth/login", json={"email": "emp@t.demo", "password": "nope"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "authentication_failed" and "don't match" in body["detail"]
    assert body["requestId"]


async def test_requires_auth(client: httpx.AsyncClient) -> None:
    r = await client.get("/leaves/mine")
    assert r.status_code == 401 and r.json()["detail"] == "Please sign in to continue."


# ---------------------------------------------------------------- submit + validation
async def test_short_leave_single_manager_step(client: httpx.AsyncClient, org: Org) -> None:
    r = await apply(client, org, "emp", 5, 7)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["employeeName"] == "Emp"  # the brief's payload field
    assert body["status"] == "PENDING_MANAGER" and body["totalDays"] == 3
    assert [s["approverName"] for s in body["steps"]] == ["Mgr"]
    assert body["allowedActions"] == ["CANCEL"]


async def test_validation_errors_are_per_field(client: httpx.AsyncClient, org: Org) -> None:
    r = await apply(client, org, "emp", 5, 2, reason="x")
    assert r.status_code == 422
    assert set(r.json()["fields"]) >= {"toDate", "reason"}


async def test_missing_field_message(client: httpx.AsyncClient, org: Org) -> None:
    r = await client.post("/leaves", headers=org.h("emp"), data={"fromDate": d(1)})
    assert r.status_code == 422
    assert r.json()["fields"]["toDate"] == "This field is required."


async def test_long_leave_requires_documents(client: httpx.AsyncClient, org: Org) -> None:
    r = await apply(client, org, "emp", 5, 8)  # 4 days
    assert r.status_code == 422 and r.json()["code"] == "documents_required"
    r = await apply(client, org, "emp", 5, 8, files=[PDF])
    assert r.status_code == 201
    body = r.json()
    assert body["requiresDocuments"] is True
    assert [(s["approverName"], s["approverRole"]) for s in body["steps"]] == [
        ("Mgr", "MANAGER"),
        ("Hod", "HOD"),
    ]


async def test_rejects_unsupported_file(client: httpx.AsyncClient, org: Org) -> None:
    r = await apply(client, org, "emp", 5, 8, files=[("evil.exe", b"MZ", "application/x-msdos")])
    assert r.status_code == 422 and "isn't supported" in r.json()["fields"]["documents"]


async def test_overlap_is_rejected(client: httpx.AsyncClient, org: Org) -> None:
    assert (await apply(client, org, "emp", 5, 6)).status_code == 201
    r = await apply(client, org, "emp", 6, 7)
    assert r.status_code == 409 and r.json()["code"] == "overlapping_leave"


async def test_concurrent_duplicate_submissions_only_one_wins(
    client: httpx.AsyncClient, org: Org
) -> None:
    """The DB exclusion constraint, not the app pre-check, is the real guarantee."""
    results = await asyncio.gather(*[apply(client, org, "emp", 10, 11) for _ in range(5)])
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 1 and codes.count(409) == 4, codes


async def test_rejected_dates_can_be_reapplied(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    await act(client, org, "mgr", rid, "reject", "Peak week")
    assert (await apply(client, org, "emp", 5, 6)).status_code == 201


# ---------------------------------------------------------------- workflow
async def test_manager_approves_short_leave(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    pending = (await client.get("/approvals/pending", headers=org.h("mgr"))).json()
    assert [p["id"] for p in pending] == [rid]
    r = await act(client, org, "mgr", rid, "approve", "Enjoy!")
    assert r.json()["status"] == "APPROVED"
    assert r.json()["comments"][0]["body"] == "Enjoy!"


async def test_two_level_approval(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 9, files=[PDF])).json()["id"]
    # HOD can't jump the queue
    r = await act(client, org, "hod", rid, "approve")
    assert r.status_code == 403
    assert (await act(client, org, "mgr", rid, "approve")).json()["status"] == "PENDING_HOD"
    assert [
        p["id"] for p in (await client.get("/approvals/pending", headers=org.h("hod"))).json()
    ] == [rid]
    assert (await client.get("/approvals/pending", headers=org.h("mgr"))).json() == []
    r = await act(client, org, "hod", rid, "approve", "OK")
    assert r.json()["status"] == "APPROVED"
    assert [s["decision"] for s in r.json()["steps"]] == ["APPROVED", "APPROVED"]


async def test_hod_rejection(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 9, files=[PDF])).json()["id"]
    await act(client, org, "mgr", rid, "approve")
    r = await act(client, org, "hod", rid, "reject", "Audit week")
    assert r.json()["status"] == "REJECTED"


async def test_reject_requires_comment(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    r = await act(client, org, "mgr", rid, "reject", "  ")
    assert r.status_code == 422 and "comment" in r.json()["fields"]


async def test_request_info_round_trip(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 9, files=[PDF])).json()["id"]
    await act(client, org, "mgr", rid, "approve")
    r = await act(client, org, "hod", rid, "request-info", "Which hospital?")
    assert r.json()["status"] == "INFO_REQUESTED"
    detail = (await client.get(f"/leaves/{rid}", headers=org.h("emp"))).json()
    assert set(detail["allowedActions"]) == {"RESPOND", "CANCEL"}
    # HOD can't approve while waiting on the employee
    assert (await act(client, org, "hod", rid, "approve")).status_code == 403
    r = await client.post(
        f"/leaves/{rid}/respond",
        headers=org.h("emp"),
        data={"comment": "Apollo, report attached"},
        files=[("documents", ("report.png", b"\x89PNG..", "image/png"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING_HOD"  # back to whoever asked
    assert len(r.json()["attachments"]) == 2
    assert (await act(client, org, "hod", rid, "approve")).json()["status"] == "APPROVED"


async def test_cancel(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    r = await client.post(f"/leaves/{rid}/cancel", headers=org.h("emp"))
    assert r.json()["status"] == "CANCELLED"
    assert r.json()["steps"][0]["decision"] == "SKIPPED"
    assert (await client.post(f"/leaves/{rid}/cancel", headers=org.h("emp"))).status_code == 409


async def test_final_state_is_immutable(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    await act(client, org, "mgr", rid, "approve")
    r = await client.post(f"/leaves/{rid}/cancel", headers=org.h("emp"))
    assert r.status_code == 409 and "already approved" in r.json()["detail"]


async def test_stale_version_is_rejected(client: httpx.AsyncClient, org: Org) -> None:
    created = (await apply(client, org, "emp", 5, 6)).json()
    r = await act(client, org, "mgr", created["id"], "approve", version=created["version"] + 5)
    assert r.status_code == 409 and r.json()["code"] == "stale_request"


# ---------------------------------------------------------------- routing edge cases
async def test_manager_is_hod_routes_level2_to_hr(client: httpx.AsyncClient, org: Org) -> None:
    body = (await apply(client, org, "crew", 5, 9, files=[PDF])).json()
    assert [(s["approverName"], s["approverRole"]) for s in body["steps"]] == [
        ("Lead", "MANAGER"),
        ("Hr", "HR_ADMIN"),
    ]


async def test_no_self_approval_for_hod(client: httpx.AsyncClient, org: Org) -> None:
    body = (await apply(client, org, "hod", 5, 9, files=[PDF])).json()
    assert all(s["approverName"] != "Hod" for s in body["steps"])


# ---------------------------------------------------------------- privacy / RBAC
async def test_peers_cannot_see_each_others_leave(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    assert (await client.get(f"/leaves/{rid}", headers=org.h("peer"))).status_code == 404
    assert (await client.get(f"/leaves/{rid}", headers=org.h("hr"))).status_code == 200


async def test_employee_cannot_approve(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 6)).json()["id"]
    r = await act(client, org, "emp", rid, "approve")
    assert r.status_code == 403 and "your own" in r.json()["detail"]


async def test_documents_are_access_controlled_and_audited(
    client: httpx.AsyncClient, org: Org
) -> None:
    body = (await apply(client, org, "emp", 5, 9, files=[PDF])).json()
    att = body["attachments"][0]["id"]
    r = await client.get(f"/attachments/{att}", headers=org.h("mgr"))
    assert r.status_code == 200 and r.content == PDF[1]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert (await client.get(f"/attachments/{att}", headers=org.h("outsider"))).status_code == 404
    audit = (await client.get("/admin/audit?action=document", headers=org.h("hr"))).json()
    assert audit and audit[0]["action"] == "document.viewed"


async def test_admin_area_is_hr_only(client: httpx.AsyncClient, org: Org) -> None:
    assert (await client.get("/admin/requests", headers=org.h("mgr"))).status_code == 403
    assert (await client.get("/admin/stats", headers=org.h("hr"))).status_code == 200


# ---------------------------------------------------------------- audit trail
async def test_timeline_records_every_transition(client: httpx.AsyncClient, org: Org) -> None:
    rid = (await apply(client, org, "emp", 5, 9, files=[PDF])).json()["id"]
    await act(client, org, "mgr", rid, "approve")
    await act(client, org, "hod", rid, "approve")
    tl = (await client.get(f"/leaves/{rid}/timeline", headers=org.h("emp"))).json()
    assert [e["action"] for e in tl] == ["leave.submitted", "leave.approve", "leave.approve"]
    assert tl[1]["before"]["status"] == "PENDING_MANAGER"
    assert tl[1]["after"]["status"] == "PENDING_HOD"
    assert all(e["correlationId"] for e in tl)


async def test_audit_log_is_append_only_in_the_database(app: object, org: Org) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.core.db import get_engine

    async with get_engine().begin() as conn:
        await conn.execute(
            text("INSERT INTO audit_logs (channel, action, entity) VALUES ('system', 'x', 'y')")
        )
    with pytest.raises(DBAPIError, match="append-only"):
        async with get_engine().begin() as conn:
            await conn.execute(text("UPDATE audit_logs SET action = 'tampered'"))


async def test_health_and_ready(app: object) -> None:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/health")).json() == {"status": "ok"}
        assert (await c.get("/ready")).json()["database"] == "ok"
