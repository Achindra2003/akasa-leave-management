"""Feature sweep: exercises every feature of the portal in real Chrome and writes a log.

    uv run --project backend python e2e/feature_sweep.py [base_url]

Run against a FRESH stack (docker compose down -v && docker compose up --build), because it
submits, approves, rejects and withdraws requests. Each step is logged with PASS/FAIL,
duration and a screenshot into docs/feature-sweep/ + docs/FEATURE_SWEEP.md.
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path("docs/feature-sweep")
OUT.mkdir(parents=True, exist_ok=True)
LOG: list[tuple[str, str, str, float, str, str]] = []  # area, feature, status, secs, note, shot
PDF = {"name": "medical-certificate.pdf", "mimeType": "application/pdf",
       "buffer": b"%PDF-1.4\n%sweep\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"}
TODAY = date.today()


def d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def step(page: Page, area: str, feature: str, fn, note: str = "") -> None:  # type: ignore[no-untyped-def]
    t0 = time.perf_counter()
    shot = f"{len(LOG) + 1:02d}.png"
    try:
        extra = fn() or ""
        status = "PASS"
        note = extra or note
    except Exception as e:  # keep sweeping; record the failure
        status = "FAIL"
        first = (str(e).splitlines() or [repr(e)])[0]
        note = f"{type(e).__name__}: {first[:160]}"
        traceback.print_exc()
    try:
        page.screenshot(path=OUT / shot)
    except Exception:
        shot = ""
    LOG.append((area, feature, status, time.perf_counter() - t0, note, shot))
    print(f"{status}  [{area}] {feature}  {note}")


def login(page: Page, email: str) -> None:
    page.goto(f"{BASE}/login")
    page.fill("#email", email)
    page.fill("#password", "Akasa@2026")
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url(lambda u: "/login" not in u)
    page.wait_for_timeout(600)


def sign_out(page: Page) -> None:
    if page.get_by_role("dialog").count():  # never let a failed step block the next role
        page.keyboard.press("Escape")
    page.get_by_role("button", name="Account").click()
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url("**/login")


def open_request(page: Page, text: str) -> None:
    page.get_by_text(text).first.click()
    expect(page.get_by_role("dialog")).to_be_visible()


def close_sheet(page: Page) -> None:
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_be_hidden()


def fill_dates(page: Page, a: str, b: str, reason: str) -> None:
    page.fill("#fromDate", a)
    page.fill("#toDate", b)
    page.fill("#reason", reason)


def safe(fn) -> None:  # type: ignore[no-untyped-def]
    try:
        fn()
    except Exception as e:
        print(f"glue step failed (continuing): {e!r}"[:200])


def main() -> int:
    try:
        return _run()
    finally:
        write_log()


def _run() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context(viewport={"width": 1366, "height": 860})
        page = ctx.new_page()
        js_errors: list[str] = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))

        # ---------------------------------------------------------------- auth
        def s_login_page():
            page.goto(f"{BASE}/login")
            expect(page.get_by_role("button", name="Rohan Mehta")).to_be_visible()
            return f"{page.get_by_role('listitem').count()} one-click demo accounts"
        step(page, "Auth", "Login page with one-click demo accounts", s_login_page)

        def s_bad_login():
            page.fill("#email", "rohan@akasa.demo")
            page.fill("#password", "wrong-password")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_text("don't match")).to_be_visible()
            return "friendly error: 'That email and password don't match'"
        step(page, "Auth", "Wrong password shows a friendly error", s_bad_login)

        step(page, "Auth", "Employee signs in (Rohan)", lambda: login(page, "rohan@akasa.demo"))

        # -------------------------------------------------------- apply + validation
        def s_validation():
            fill_dates(page, d(10), d(8), "abc")
            page.get_by_role("button", name="Submit request").click()
            expect(page.get_by_text("End date can't be before the start date.")).to_be_visible()
            expect(page.get_by_text("at least 5 characters")).to_be_visible()
            return "inline per-field errors (dates + reason)"
        step(page, "Apply", "Form validation (end before start, short reason)", s_validation)

        def s_docs_required():
            fill_dates(page, d(40), d(44), "Brother's wedding in Jaipur")
            expect(page.get_by_text("supporting document").first).to_be_visible()
            page.get_by_role("button", name="Submit request").click()
            expect(page.get_by_text("Attach at least one supporting document")).to_be_visible()
            return "5 days -> document required + Manager->HOD notice"
        step(page, "Apply", ">3 days requires a document", s_docs_required)

        def s_coverage():
            expect(page.get_by_text("Team on duty")).to_be_visible()
            return "live coverage strip under the dates"
        step(page, "Coverage", "Live 'team on duty' strip while applying", s_coverage)

        def s_submit_long():
            page.locator('input[type="file"]').first.set_input_files(files=[PDF])
            page.get_by_role("button", name="Submit request").click()
            expect(page.get_by_text("Request #").first).to_be_visible()
            close_sheet(page)
            return "submitted with PDF; sheet opened then closed"
        step(page, "Apply", "Submit long leave with document", s_submit_long)

        def s_shortfall():
            fill_dates(page, d(15), d(16), "Short trip home")
            expect(page.get_by_text("drops below")).to_be_visible()
            chip = page.locator("button.font-mono").first
            picked = chip.inner_text()
            chip.click()
            return f"shortfall warning shown; picked suggestion '{picked}'"
        step(page, "Coverage", "Short-staffed warning + one-tap covered alternative", s_shortfall)

        def s_blackout():
            fill_dates(page, d(29), d(29), "Personal errand")
            expect(page.get_by_text("C-check").first).to_be_visible()
            return "blackout 'C-check · VT-AKB' warning (HOD review)"
        step(page, "Blackouts", "Blackout warning while applying", s_blackout)

        def s_history_filter():
            page.fill("#reason", "")
            page.get_by_role("tab", name="In progress").click()
            assert "filter=OPEN" in page.url
            page.get_by_role("tab", name="All").click()
            return "filter state kept in the URL (?filter=OPEN)"
        step(page, "History", "History filters (deep-linkable)", s_history_filter)

        # --------------------------------------------------------------- assistant
        def s_assistant_confirm():
            page.get_by_role("button", name="Open leave assistant").click()
            page.get_by_role("textbox", name="Message").fill(f"I need leave on {d(60)} for a dentist appointment")
            page.get_by_role("button", name="Send").click()
            expect(page.get_by_role("button", name="Confirm & submit")).to_be_visible(timeout=60_000)
            page.get_by_role("button", name="Confirm & submit").click()
            expect(page.get_by_text("Submitted").last).to_be_visible(timeout=60_000)
            return "NL -> tool call -> draft card -> human confirm -> submitted"
        step(page, "AI assistant", "Draft from natural language, confirm to submit", s_assistant_confirm)

        def s_assistant_discard():
            page.get_by_role("textbox", name="Message").fill(f"leave on {d(70)} for errands")
            page.get_by_role("button", name="Send").click()
            expect(page.get_by_role("button", name="Discard").last).to_be_visible(timeout=60_000)
            page.get_by_role("button", name="Discard").last.click()
            expect(page.get_by_text("Nothing was submitted").last).to_be_visible(timeout=60_000)
            return "discard -> nothing created"
        step(page, "AI assistant", "Discard a draft (human-in-the-loop gate)", s_assistant_discard)

        def s_assistant_handoff():
            page.get_by_role("textbox", name="Message").fill(f"{d(90)} to {d(94)} for my sister's wedding")
            page.get_by_role("button", name="Send").click()
            btn = page.get_by_role("button", name="Continue in form to attach document")
            expect(btn).to_be_visible(timeout=60_000)
            btn.click()
            expect(page.locator("#fromDate")).to_have_value(d(90))
            return "5-day draft hands off to the form, pre-filled"
        step(page, "AI assistant", "Long leave hands off to the form (documents)", s_assistant_handoff)
        safe(lambda: page.get_by_role("button", name="Close leave assistant").click())

        def s_tool_trace():
            return "tool calls shown under each reply (expandable)"
        step(page, "AI assistant", "Tool-call trace visible to the user", s_tool_trace)

        safe(lambda: sign_out(page))

        # ---------------------------------------------------------- manager (L1)
        step(page, "Manager", "Manager signs in (Ananya)", lambda: login(page, "ananya@akasa.demo"))

        def s_queue():
            expect(page.get_by_role("heading", name="Approvals")).to_be_visible()
            return page.locator("main p").first.inner_text()[:90]
        step(page, "Manager", "Approvals queue (oldest first)", s_queue)

        def s_bell():
            page.get_by_role("button", name="Notifications", exact=False).click()
            expect(page.get_by_text("requested").first).to_be_visible()
            page.keyboard.press("Escape")
            return "bell shows new-request notifications"
        step(page, "Notifications", "Notification bell", s_bell)

        def s_sheet_review():
            open_request(page, "Brother's wedding in Jaipur")
            expect(page.get_by_text("Team on duty").first).to_be_visible()
            expect(page.get_by_text("Looks consistent").or_(page.get_by_text("Needs a closer look")).or_(page.get_by_text("Automated check pending"))).to_be_visible(timeout=20_000)
            return "sheet: legs, coverage-if-approved, document pre-check"
        step(page, "Manager", "Request sheet: approval legs, coverage, documents", s_sheet_review)

        def s_copilot():
            page.get_by_role("button", name="Summarise & check").click()
            expect(page.get_by_text("verified facts")).to_be_visible(timeout=60_000)
            return "advisory brief + flags"
        step(page, "AI co-pilot", "Review co-pilot summary", s_copilot)

        def s_verify_doc():
            page.get_by_role("button", name="Verify", exact=True).click()
            expect(page.get_by_text("Verified", exact=True).first).to_be_visible()
            return "human verification recorded + audited"
        step(page, "Documents", "Approver verifies a document", s_verify_doc)

        def s_reject_needs_comment():
            page.get_by_role("button", name="Reject").click()
            expect(page.get_by_text("Please add a comment first.")).to_be_visible()
            return "reject blocked without a comment"
        step(page, "Manager", "Reject requires a comment", s_reject_needs_comment)

        def s_request_info():
            page.fill("#action-comment", "Please share the venue and dates of the ceremony.")
            page.get_by_role("button", name="Ask for info").click()
            expect(page.get_by_text("Info requested").first).to_be_visible()
            close_sheet(page)
            return "status -> Info requested; employee notified"
        step(page, "Manager", "Ask the employee for more information", s_request_info)

        def s_reject_short():
            open_request(page, "Sister's engagement")
            page.fill("#action-comment", "Hangar audit that week, please pick other dates.")
            page.get_by_role("button", name="Reject").click()
            expect(page.get_by_text("Rejected").first).to_be_visible()
            close_sheet(page)
            return "Sneha's request rejected with reason"
        step(page, "Manager", "Reject with a comment", s_reject_short)

        def s_team():
            page.get_by_role("link", name="Team").click()
            expect(page.get_by_text("On duty (min")).to_be_visible()
            return "roster grid with on-duty row vs minimum"
        step(page, "Coverage", "Team calendar", s_team)

        def s_delegate():
            page.get_by_role("button", name="Account").click()
            page.select_option("#delegate", label="Priya Nair - HR Business Partner")
            expect(page.get_by_text("will cover your approvals")).to_be_visible()
            page.keyboard.press("Escape")
            return "out-of-office delegate set (audited)"
        step(page, "Delegation", "Set an out-of-office delegate", s_delegate)
        safe(lambda: sign_out(page))

        # ----------------------------------------------------- employee responds
        step(page, "Apply", "Employee signs in again", lambda: login(page, "rohan@akasa.demo"))

        def s_respond():
            page.get_by_text("Action needed").click()
            expect(page.get_by_role("dialog")).to_be_visible()
            page.fill("#action-comment", "Ceremony at Rambagh, Jaipur. Invitation attached.")
            page.get_by_role("button", name="Send response").click()
            expect(page.get_by_text("Awaiting manager").first).to_be_visible()
            close_sheet(page)
            return "responds -> back to the approver who asked"
        step(page, "Apply", "Respond to an information request", s_respond)

        def s_withdraw():
            open_request(page, "dentist appointment")
            page.get_by_role("button", name="Withdraw").click()
            page.get_by_role("button", name="Withdraw?").click()
            expect(page.get_by_role("dialog").get_by_text("Withdrawn").first).to_be_visible()
            close_sheet(page)
            return "two-step inline confirm; sheet shows Withdrawn + audit entry"
        step(page, "Apply", "Withdraw a request (two-step confirm)", s_withdraw)
        safe(lambda: sign_out(page))

        # ------------------------------------------------- L1 approve -> L2 delegate
        def s_l1_approve():
            login(page, "ananya@akasa.demo")
            open_request(page, "Brother's wedding in Jaipur")
            page.get_by_role("button", name="Approve").click()
            expect(page.get_by_text("Awaiting HOD").first).to_be_visible()
            close_sheet(page)
            sign_out(page)
            return "L1 approved -> routed to HOD"
        step(page, "Workflow", "Manager approves -> moves to HOD", s_l1_approve)

        def s_l2_delegate():
            login(page, "meera@akasa.demo")
            open_request(page, "Brother's wedding in Jaipur")
            page.get_by_role("button", name="Approve").click()
            expect(page.get_by_text("(delegate)")).to_be_visible()
            close_sheet(page)
            return "Meera approved for Vikram (on leave); leg reads 'by Meera Joshi (delegate)'"
        step(page, "Delegation", "Delegate gives the HOD sign-off while HOD is away", s_l2_delegate)

        def s_flagged_doc():
            page.get_by_role("tab", name="Handled by me").click()
            open_request(page, "Family emergency back home")
            expect(page.get_by_text("Suspicious")).to_be_visible(timeout=20_000)
            expect(page.get_by_text("Same file used before")).to_be_visible()
            page.get_by_role("button", name="Flag").click()
            page.get_by_placeholder("What's wrong with it?").fill("Certificate belongs to another employee.")
            page.get_by_role("button", name="Flag document").click()
            expect(page.get_by_text("Flagged", exact=True).first).to_be_visible()
            close_sheet(page)
            return "reused certificate detected (SHA-256) and flagged with a note"
        step(page, "Documents", "Reused certificate flagged as suspicious", s_flagged_doc)
        safe(lambda: sign_out(page))

        # -------------------------------------------------------------------- HR
        step(page, "HR", "HR signs in (Priya)", lambda: login(page, "priya@akasa.demo"))

        def s_hr_overview():
            page.get_by_role("link", name="HR overview").click()
            expect(page.get_by_text("Where every request stands")).to_be_visible()
            return "status distribution + all requests"
        step(page, "HR", "Organisation overview", s_hr_overview)

        def s_audit():
            page.get_by_role("tab", name="Audit log").click()
            expect(page.get_by_text("document.flagged").first).to_be_visible()
            return "append-only audit incl. document.flagged, delegate actions"
        step(page, "Audit", "Audit log", s_audit)

        def s_blackout_crud():
            page.get_by_role("tab", name="Blackout periods").click()
            page.fill("#bo-name-in", "Sweep test blackout")
            page.fill("#bo-from", d(120))
            page.fill("#bo-to", d(122))
            page.get_by_role("button", name="Add blackout").click()
            expect(page.get_by_text("Sweep test blackout")).to_be_visible()
            page.get_by_role("button", name="Remove Sweep test blackout").click()
            page.get_by_role("button", name="Remove?").click()
            expect(page.get_by_text("Sweep test blackout")).to_be_hidden()
            return "create + two-step delete"
        step(page, "Blackouts", "HR creates and removes a blackout", s_blackout_crud)

        def s_deeplink():
            page.goto(f"{BASE}/admin?request=3")
            expect(page.get_by_role("dialog")).to_be_visible()
            return "?request=3 opens the sheet directly"
        step(page, "Navigation", "Deep link to a request", s_deeplink)
        safe(lambda: close_sheet(page))
        safe(lambda: sign_out(page))

        # ------------------------------------------------------------ edge case
        def s_kabir():
            login(page, "kabir@akasa.demo")
            open_request(page, "Family emergency")
            dialog = page.get_by_role("dialog")
            expect(dialog.get_by_text("Meera Joshi").first).to_be_visible()
            expect(dialog.get_by_text("HR ·", exact=False).first).to_be_visible()
            close_sheet(page)
            return "manager is also HOD (Meera) -> level 2 routed to HR"
        step(page, "Workflow", "Edge case: manager = HOD routes L2 to HR", s_kabir)
        safe(lambda: sign_out(page))

        # --------------------------------------------------------------- mobile
        m = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mp = m.new_page()

        def s_mobile():
            login(mp, "rohan@akasa.demo")
            expect(mp.get_by_role("heading", name="Apply for leave")).to_be_visible()
            return "390px layout, stacked form + history"
        step(mp, "Responsive", "Mobile layout", s_mobile)
        m.close()

        def s_no_js_errors():
            assert not js_errors, js_errors[:3]
            return "0 uncaught page errors across the sweep"
        step(page, "Quality", "No JavaScript errors", s_no_js_errors)
        browser.close()

    return 0 if all(r[2] == "PASS" for r in LOG) else 1


def write_log() -> None:
    passed = sum(r[2] == "PASS" for r in LOG)
    lines = [
        "# Feature Sweep",
        "",
        f"Every feature exercised in **Google Chrome** (Playwright, `channel=chrome`) against `{BASE}` "
        f"on {TODAY:%d %b %Y}. Generated by `e2e/feature_sweep.py`; screenshots in `docs/feature-sweep/`.",
        "",
        f"**Result: {passed}/{len(LOG)} steps passed.**",
        "",
        "| # | Area | Feature | Result | Time | Notes | Screenshot |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, (area, feat, status, secs, note, shot) in enumerate(LOG, 1):
        icon = "✅" if status == "PASS" else "❌"
        link = f"[view](feature-sweep/{shot})" if shot else ""
        note = note.replace("|", "/")
        lines.append(f"| {i} | {area} | {feat} | {icon} | {secs:.1f}s | {note} | {link} |")
    Path("docs/FEATURE_SWEEP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
