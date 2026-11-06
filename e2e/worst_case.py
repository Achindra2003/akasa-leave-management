"""Worst-case dataset for the break-ui pass (kept as a regression fixture).

Enters through the real boundaries: users are inserted into the database (there is no
user-admin API), leave requests go through the HTTP API like a real client.
Values are realistic or schema-limit-backed, never random noise:
  * name: String(120)  * reason: 500 chars  * comment: 1000  * filename: 255

Usage:  uv run --project backend python e2e/worst_case.py [base_url] [db_url]
"""

import sys
from datetime import date, timedelta

import httpx
import psycopg

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DB = sys.argv[2] if len(sys.argv) > 2 else "postgresql://leave:leave@localhost:5432/leave"
API = f"{BASE}/api/v1"

PEOPLE = [
    # (name, email-local, title)
    ("Aleksandra Wiśniewska-Kowalczyk", "aleksandra.wisniewska-kowalczyk", "Senior Aircraft Maintenance Engineer (B1/B2 Licensed, A320neo Family)"),
    ("Jo", "jo", None),
    ("Nguyễn Thị Phương Thảo", "thao.nguyen", "Avionics Technician"),
    ("Venkatanarasimharajuvaripeta Subrahmanyam Lakshminarasimhan", "lakshminarasimhan.subrahmanyam", "Structures Technician"),
    ("श्रीनिवासन वेंकटरामन", "srinivasan.venkataraman", "Line Engineer"),
    ("Bartholomew Fitzgerald-Montgomery III", "bartholomew.fitzgerald-montgomery", "Technical Records Officer"),
]
for i in range(9):  # a realistically large line-maintenance team
    PEOPLE.append((f"Engineer {i + 1:02d} Ramachandran", f"eng{i + 1:02d}", "Licensed Engineer"))

LONG_REASON = (
    "Post-operative recovery after arthroscopic knee surgery (ACL reconstruction) at "
    "Apollo Hospitals, Bannerghatta Road. Discharge summary and physiotherapy schedule: "
    "https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefGHIJ/view?usp=sharing "
    "- the orthopaedic surgeon has advised no weight-bearing work, no ladder or hangar-floor "
    "duty and no night shifts for the full period; I'll be reachable on phone for handover "
    "questions about the open defects on VT-AKB and VT-AKC."
)[:500]
LONG_FILE = "Apollo-Hospitals-Bengaluru-Discharge-Summary-and-Medical-Fitness-Certificate-ACL-Reconstruction-Final-Signed-v3.pdf"


def main() -> None:
    pw_hash = None
    with psycopg.connect(DB, autocommit=True) as conn:
        mgr = conn.execute("SELECT id, department_id, password_hash FROM users WHERE email='ananya@akasa.demo'").fetchone()
        assert mgr, "seed data missing"
        mgr_id, dept, pw_hash = mgr
        for name, local, title in PEOPLE:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role, title, manager_id, department_id) "
                "VALUES (%s, %s, %s, 'EMPLOYEE', %s, %s, %s) ON CONFLICT (email) DO NOTHING",
                (name, f"{local}@akasa.demo", pw_hash, title, mgr_id, dept),
            )

    today = date.today()
    pdf = b"%PDF-1.4\n%worst-case\n"
    with httpx.Client(base_url=API, timeout=30) as c:
        def token(local: str) -> dict[str, str]:
            r = c.post("/auth/login", json={"email": f"{local}@akasa.demo", "password": "Akasa@2026"})
            r.raise_for_status()
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}

        def apply(local: str, start: int, days: int, reason: str, fname: str | None = None) -> None:
            f = today + timedelta(days=start)
            files = [("documents", (fname, pdf, "application/pdf"))] if fname else []
            r = c.post("/leaves", headers=token(local), files=files or None,
                       data={"fromDate": f.isoformat(), "toDate": (f + timedelta(days=days - 1)).isoformat(),
                             "reason": reason})
            print(local, r.status_code, r.json().get("detail", "") if r.status_code >= 400 else "")

        apply("aleksandra.wisniewska-kowalczyk", 9, 30, LONG_REASON, LONG_FILE)  # max span
        apply("jo", 10, 1, "Exam")  # shortest plausible reason (5-char min)
        apply("thao.nguyen", 10, 4, "Đám cưới của em gái ở Đà Nẵng - lễ ăn hỏi và tiệc cưới", "giấy-mời-đám-cưới.pdf")
        apply("lakshminarasimhan.subrahmanyam", 11, 2, "Upanayanam ceremony of my nephew in Tirupati")
        apply("srinivasan.venkataraman", 10, 3, "परिवार में शादी - वाराणसी जाना है")
        apply("bartholomew.fitzgerald-montgomery", 12, 5, "Jury duty, Bengaluru Urban District Court", "summons.pdf")
        for i in range(9):  # everyone off the same week -> coverage collapses
            apply(f"eng{i + 1:02d}", 10 + (i % 3), 2, "Diwali travel home")


if __name__ == "__main__":
    main()
