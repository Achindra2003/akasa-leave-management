"""Production verification that does not disturb the seeded demo story.

    uv run --project backend python e2e/prod_check.py https://akasa-leave.onrender.com

Checks: health, auth per role, RBAC/privacy, every read surface, the live LLM assistant
(draft -> DISCARD, nothing submitted), live co-pilot, security controls (headers, upload
sniffing, rate limiting), and latency under modest concurrent load. Exits non-zero on failure.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from datetime import date, timedelta

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://akasa-leave.onrender.com").rstrip("/")
API = f"{BASE}/api/v1"
PW = "Akasa@2026"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


async def main() -> int:
    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        h = (await c.get(f"{BASE}/ready")).json()
        check("ready (db reachable)", h.get("database") == "ok", str(h))
        ai = (await c.get("/ai/status")).json()
        check("AI live on Groq, Postgres checkpointer", ai.get("live") and ai.get("checkpointer") == "postgres", str(ai))

        tok: dict[str, dict[str, str]] = {}
        for who in ("rohan", "ananya", "vikram", "meera", "priya", "kabir"):
            r = await c.post("/auth/login", json={"email": f"{who}@akasa.demo", "password": PW})
            ok = r.status_code == 200
            if ok:
                tok[who] = {"Authorization": f"Bearer {r.json()['accessToken']}"}
            check(f"login {who}", ok, str(r.status_code))

        # read surfaces per role
        mine = (await c.get("/leaves/mine", headers=tok["rohan"])).json()
        check("employee history", isinstance(mine, list) and len(mine) >= 1, f"{len(mine)} requests")
        pend = (await c.get("/approvals/pending", headers=tok["meera"])).json()
        check("delegate sees HOD queue (Meera covers Vikram)",
              any(p["employeeName"] == "Rohan Mehta" for p in pend), f"{len(pend)} pending")
        cal = (await c.get("/coverage/team?days=28", headers=tok["ananya"])).json()
        check("team calendar", cal.get("teamSize", 0) >= 4, f"team {cal.get('teamSize')}, min {cal.get('minAvailable')}")
        for path in ("/admin/stats", "/admin/audit?limit=5", "/blackouts", "/notifications"):
            r = await c.get(path, headers=tok["priya"])
            check(f"HR read {path}", r.status_code == 200)

        # RBAC / privacy
        kabir_req = (await c.get("/leaves/mine", headers=tok["kabir"])).json()[0]["id"]
        r = await c.get(f"/leaves/{kabir_req}", headers=tok["rohan"])
        check("peer can't read another's request (404, no existence leak)", r.status_code == 404)
        r = await c.get("/admin/audit", headers=tok["rohan"])
        check("employee blocked from HR audit", r.status_code == 403)
        r = await c.get("/leaves/mine")
        check("no token -> 401 problem+json", r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json"))

        # security controls
        r = await c.get("/policy")
        hdr = r.headers
        check("security headers (CSP, XFO, HSTS, nosniff)",
              "frame-ancestors 'none'" in hdr.get("content-security-policy", "")
              and hdr.get("x-frame-options") == "DENY"
              and "max-age" in hdr.get("strict-transport-security", "")
              and hdr.get("x-content-type-options") == "nosniff")
        far = date.today() + timedelta(days=200)
        r = await c.post("/leaves", headers=tok["rohan"],
                         data={"fromDate": far.isoformat(), "toDate": (far + timedelta(days=4)).isoformat(),
                               "reason": "Security check - disguised executable"},
                         files=[("documents", ("certificate.pdf", b"MZ\x90\x00not-a-pdf", "application/pdf"))])
        check("disguised .exe upload rejected (nothing written)", r.status_code == 422, r.json().get("fields", {}).get("documents", ""))
        codes = []
        for _ in range(11):
            r = await c.post("/auth/login", json={"email": "ratelimit-probe@akasa.demo", "password": "x"})
            codes.append(r.status_code)
        check("login brute-force rate limited", codes[-1] == 429 and codes[0] == 401, f"{codes.count(401)}x401 then {codes[-1]}")

        # live AI: draft then DISCARD (no request created)
        day = date.today() + timedelta(days=45)
        t0 = time.perf_counter()
        r = await c.post("/ai/assistant/chat", headers=tok["rohan"],
                         json={"message": f"I need leave on {day.isoformat()} for a dentist appointment"})
        out = r.json()
        ms = int((time.perf_counter() - t0) * 1000)
        draft = out.get("draft") or {}
        check("live assistant drafts via tool", out.get("awaitingConfirmation") and draft.get("fromDate") == day.isoformat(),
              f"{ms}ms, tools={[s['tool'] for s in out.get('steps', []) if s['type'] == 'tool_call']}")
        wd = day.strftime("%a")
        mentioned = [w for w in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") if w in out.get("reply", "")]
        check("assistant weekday not hallucinated", not mentioned or mentioned == [wd], f"expected {wd}, reply mentions {mentioned or 'none'}")
        before = len((await c.get("/leaves/mine", headers=tok["rohan"])).json())
        r = await c.post("/ai/assistant/confirm", headers=tok["rohan"], json={"threadId": out["threadId"], "approve": False})
        after = len((await c.get("/leaves/mine", headers=tok["rohan"])).json())
        check("discard submits nothing (human gate)", r.status_code == 200 and before == after, r.json().get("reply", "")[:60])

        # live co-pilot (read-only advisory)
        rohan_req = next(p["id"] for p in pend if p["employeeName"] == "Rohan Mehta")
        t0 = time.perf_counter()
        r = await c.get(f"/ai/copilot/{rohan_req}", headers=tok["meera"])
        cp = r.json()
        check("live co-pilot brief", r.status_code == 200 and cp.get("summary") and cp.get("liveModel"),
              f"{int((time.perf_counter() - t0) * 1000)}ms, recommendation={cp.get('recommendation')}, flags={len(cp.get('flags', []))}")

        # modest load: 200 authenticated reads, 20 concurrent
        lat: list[float] = []
        errors = 0
        sem = asyncio.Semaphore(20)

        async def one(i: int) -> None:
            nonlocal errors
            async with sem:
                t = time.perf_counter()
                path = ("/leaves/mine", "/approvals/pending", "/policy", "/notifications")[i % 4]
                who = ("rohan", "ananya", "rohan", "meera")[i % 4]
                rr = await c.get(path, headers=tok[who])
                lat.append((time.perf_counter() - t) * 1000)
                errors += rr.status_code >= 500

        t0 = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(200)))
        wall = time.perf_counter() - t0
        lat.sort()
        p50, p95, p99 = lat[100], lat[189], lat[197]
        check("load: 200 reads @20 concurrent, 0 errors", errors == 0,
              f"{200 / wall:.0f} req/s, p50 {p50:.0f}ms, p95 {p95:.0f}ms, p99 {p99:.0f}ms, mean {statistics.mean(lat):.0f}ms")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
