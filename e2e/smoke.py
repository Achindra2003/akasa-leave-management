"""E2E smoke test: drives the real UI through the core workflow in a headless browser.

Usage:  uv run --project backend python e2e/smoke.py [base_url] [screenshot_dir]
Uses an installed Chrome/Edge (no browser download). Exits non-zero on failure.
"""

import random
import sys
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
REASON = f"Brother's wedding in Jaipur (run {random.randint(1000, 9999)})"


def launch(p):
    for channel in ("msedge", "chrome", None):
        try:
            return p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        except Exception:
            continue
    raise SystemExit("No Chromium-based browser found")


def login(page, name):
    page.goto(f"{BASE}/login")
    page.get_by_role("button", name=name).click()
    page.wait_for_url(lambda u: "/login" not in u)


with sync_playwright() as p:
    browser = launch(p)
    ctx = browser.new_context(viewport={"width": 1366, "height": 860})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        run_flow = True

        page.goto(f"{BASE}/login")
        expect(page.get_by_text("Time off, cleared for departure.")).to_be_visible()
        page.screenshot(path=OUT / "01-login.png")

        # Employee applies for a 5-day leave -> document required
        login(page, "Rohan Mehta")
        expect(page.get_by_role("heading", name="Apply for leave")).to_be_visible()
        start = date.today() + timedelta(days=random.randint(60, 300))  # re-runnable
        page.locator('input[name="fromDate"]').fill(start.isoformat())
        page.locator('input[name="toDate"]').fill((start + timedelta(days=4)).isoformat())
        page.locator('textarea[name="reason"]').fill(REASON)
        expect(page.get_by_text("supporting document")).to_be_visible()
        page.get_by_role("button", name="Submit request").click()
        expect(page.get_by_text("Attach at least one supporting document")).to_be_visible()
        page.screenshot(path=OUT / "02-apply-validation.png")
        page.locator('input[type="file"]').first.set_input_files(
            files=[{"name": "invitation.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 x"}]
        )
        page.get_by_role("button", name="Submit request").click()
        expect(page.get_by_text("Request #").first).to_be_visible()
        page.keyboard.press("Escape")
        page.screenshot(path=OUT / "03-employee-dashboard.png")

        # Assistant drafts a leave
        page.get_by_role("button", name="Leave assistant").click()
        confirm = page.get_by_role("button", name="Confirm & submit")
        for _ in range(6):  # a random day may collide with an earlier run's leave
            one_day = (date.today() + timedelta(days=random.randint(200, 360))).isoformat()
            page.get_by_role("textbox", name="Message").fill(
                f"I need leave on {one_day} for a dentist appointment")
            page.get_by_role("button", name="Send").click()
            page.wait_for_function("() => !document.body.innerText.includes('···')")
            if confirm.count():
                break
        expect(confirm).to_be_visible()
        page.screenshot(path=OUT / "04-assistant-draft.png")
        page.get_by_role("button", name="Confirm & submit").click()
        expect(page.get_by_text("Submitted", exact=False).last).to_be_visible()

        # Manager approves -> goes to HOD
        page.get_by_role("button", name="Sign out").click()
        login(page, "Ananya Sharma")
        expect(page.get_by_role("heading", name="Approvals")).to_be_visible()
        page.get_by_text(REASON).click()
        page.get_by_role("button", name="Summarise & check").click()
        expect(page.get_by_text("verified facts")).to_be_visible()
        page.screenshot(path=OUT / "05-approver-sheet-copilot.png")
        page.get_by_role("button", name="Approve").click()
        expect(page.get_by_text("Awaiting HOD").first).to_be_visible()
        page.keyboard.press("Escape")

        # HOD approves
        page.get_by_role("button", name="Sign out").click()
        login(page, "Vikram Rao")
        page.get_by_text(REASON).click()
        page.get_by_role("button", name="Approve").click()
        expect(page.get_by_text("Approved").first).to_be_visible()
        page.keyboard.press("Escape")

        # HR overview + audit
        page.get_by_role("button", name="Sign out").click()
        login(page, "Priya Nair")
        page.get_by_role("link", name="HR overview").click()
        page.get_by_role("tab", name="Audit log").click()
        expect(page.get_by_text("leave.approve").first).to_be_visible()
        page.screenshot(path=OUT / "06-hr-audit.png")
    except Exception:
        page.screenshot(path=OUT / "failure.png")
        raise

    # Mobile
    m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    mp = m.new_page()
    login(mp, "Rohan Mehta")
    mp.screenshot(path=OUT / "07-mobile.png", full_page=True)

    browser.close()
    if errors:
        raise SystemExit(f"JS errors: {errors}")
    print("E2E smoke passed")
