"""Security hardening: headers, upload sniffing, rate limits, document sandboxing."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import PASSWORD, Org
from tests.integration.test_leave_flow import PDF, apply

pytestmark = pytest.mark.integration


async def test_security_headers_on_api_and_spa(client: httpx.AsyncClient) -> None:
    r = await client.get("/policy")
    h = r.headers
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "script-src 'self'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["cache-control"] == "no-store"


async def test_disguised_executable_is_rejected(client: httpx.AsyncClient, org: Org) -> None:
    """A renamed .exe sent with Content-Type application/pdf must not get through."""
    fake = ("medical.pdf", b"MZ\x90\x00 this is really a windows executable", "application/pdf")
    r = await apply(client, org, "emp", 5, 9, files=[fake])
    assert r.status_code == 422
    assert "doesn't look like a real PDF" in r.json()["fields"]["documents"]


async def test_documents_are_served_sandboxed(client: httpx.AsyncClient, org: Org) -> None:
    att = (await apply(client, org, "emp", 5, 9, files=[PDF])).json()["attachments"][0]["id"]
    r = await client.get(f"/attachments/{att}", headers=org.h("mgr"))
    assert r.headers["content-security-policy"].startswith("sandbox")


async def test_login_is_rate_limited(client: httpx.AsyncClient, org: Org) -> None:
    for _ in range(10):
        r = await client.post("/auth/login", json={"email": "emp@t.demo", "password": "wrong"})
        assert r.status_code == 401
    r = await client.post("/auth/login", json={"email": "emp@t.demo", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) > 0


async def test_assistant_is_rate_limited_per_user(client: httpx.AsyncClient, org: Org) -> None:
    for _ in range(20):
        r = await client.post("/ai/assistant/chat", headers=org.h("emp"), json={"message": "hi"})
        assert r.status_code == 200
    r = await client.post("/ai/assistant/chat", headers=org.h("emp"), json={"message": "hi"})
    assert r.status_code == 429
    # another user is unaffected
    r = await client.post("/ai/assistant/chat", headers=org.h("peer"), json={"message": "hi"})
    assert r.status_code == 200
