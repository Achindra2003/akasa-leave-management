"""Idempotent demo data: a small, fictional airline org that exercises every routing edge
case (D-001) and every operational extra (D-018..D-022). All names are fictional; emails
use the ``.demo`` TLD so nothing can be mistaken for a real mailbox."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import clock
from app.core.logging import log
from app.core.security import hash_password
from app.domain.enums import Action, Role
from app.models import BlackoutPeriod, Department, LeaveRequest, User
from app.seed_docs import make_pdf
from app.services.leave_service import Actor, LeaveService, Upload

DEMO_PASSWORD = "Akasa@2026"

# Shown on the login page as one-click sign-ins.
DEMO_ACCOUNTS: list[dict[str, object]] = [
    {
        "name": "Rohan Mehta",
        "email": "rohan@akasa.demo",
        "role": Role.EMPLOYEE,
        "title": "Aircraft Maintenance Engineer",
        "blurb": "Employee. Apply, see team coverage live, upload documents.",
    },
    {
        "name": "Ananya Sharma",
        "email": "ananya@akasa.demo",
        "role": Role.MANAGER,
        "title": "Line Maintenance Manager",
        "blurb": "Manager (L1). Team calendar, approve/reject/ask for info.",
    },
    {
        "name": "Vikram Rao",
        "email": "vikram@akasa.demo",
        "role": Role.HOD,
        "title": "Head of Engineering",
        "blurb": "HOD (L2). On leave today - Meera covers his queue.",
    },
    {
        "name": "Meera Joshi",
        "email": "meera@akasa.demo",
        "role": Role.HOD,
        "title": "Head of In-flight Services",
        "blurb": "HOD + Vikram's delegate. Sees a reused certificate flagged.",
    },
    {
        "name": "Priya Nair",
        "email": "priya@akasa.demo",
        "role": Role.HR_ADMIN,
        "title": "HR Business Partner",
        "blurb": "HR admin. Org overview, blackout periods, audit log.",
    },
    {
        "name": "Kabir Singh",
        "email": "kabir@akasa.demo",
        "role": Role.EMPLOYEE,
        "title": "Cabin Crew",
        "blurb": "Edge case: manager is also HOD, so L2 routes to HR.",
    },
]


async def seed(session: AsyncSession) -> bool:
    if await session.scalar(select(func.count()).select_from(User)):
        return False
    pw = hash_password(DEMO_PASSWORD)

    def u(name: str, email: str, role: Role, title: str) -> User:
        return User(name=name, email=email, role=role, title=title, password_hash=pw)

    eng = Department(name="Engineering & Maintenance")
    ifs = Department(name="In-flight Services")
    hr_dept = Department(name="People & Culture")
    session.add_all([eng, ifs, hr_dept])
    await session.flush()

    priya = u("Priya Nair", "priya@akasa.demo", Role.HR_ADMIN, "HR Business Partner")
    arjun = u("Arjun Desai", "arjun@akasa.demo", Role.HR_ADMIN, "Head of HR")
    vikram = u("Vikram Rao", "vikram@akasa.demo", Role.HOD, "Head of Engineering")
    ananya = u("Ananya Sharma", "ananya@akasa.demo", Role.MANAGER, "Line Maintenance Manager")
    rohan = u("Rohan Mehta", "rohan@akasa.demo", Role.EMPLOYEE, "Aircraft Maintenance Engineer")
    sneha = u("Sneha Iyer", "sneha@akasa.demo", Role.EMPLOYEE, "Avionics Technician")
    dev = u("Dev Patel", "dev@akasa.demo", Role.EMPLOYEE, "B1 Licensed Engineer")
    isha = u("Isha Kulkarni", "isha@akasa.demo", Role.EMPLOYEE, "Structures Technician")
    meera = u("Meera Joshi", "meera@akasa.demo", Role.HOD, "Head of In-flight Services")
    kabir = u("Kabir Singh", "kabir@akasa.demo", Role.EMPLOYEE, "Cabin Crew")
    tara = u("Tara Menon", "tara@akasa.demo", Role.EMPLOYEE, "Cabin Crew")
    people = [priya, arjun, vikram, ananya, rohan, sneha, dev, isha, meera, kabir, tara]
    session.add_all(people)
    await session.flush()

    for p in (priya, arjun):
        p.department_id = hr_dept.id
    priya.manager_id = arjun.id
    vikram.department_id, vikram.manager_id = eng.id, arjun.id
    ananya.department_id, ananya.manager_id = eng.id, vikram.id
    for e in (rohan, sneha, dev, isha):
        e.department_id, e.manager_id = eng.id, ananya.id
    meera.department_id, meera.manager_id = ifs.id, arjun.id
    for e in (kabir, tara):
        e.department_id, e.manager_id = ifs.id, meera.id  # manager == HOD edge case
    eng.hod_id, ifs.hod_id, hr_dept.hod_id = vikram.id, meera.id, arjun.id
    vikram.delegate_id = meera.id  # covers Vikram's approvals while he's away (D-020)
    await session.commit()

    today = clock.today()

    def d(n: int) -> date:
        return today + timedelta(days=n)

    # Blackouts (D-019): a heavy-maintenance check for Engineering, and year-end peak.
    peak = date(today.year, 12, 20)
    if peak < today:
        peak = date(today.year + 1, 12, 20)
    session.add_all(
        [
            BlackoutPeriod(
                name="C-check · VT-AKB",
                department_id=eng.id,
                from_date=d(28),
                to_date=d(34),
                reason="Heavy maintenance check - all licensed engineers rostered.",
                created_by=arjun.id,
            ),
            BlackoutPeriod(
                name="Year-end peak travel",
                from_date=peak,
                to_date=peak + timedelta(days=14),
                reason="Highest passenger volume of the year.",
                created_by=arjun.id,
            ),
        ]
    )
    await session.commit()

    cert = make_pdf(
        [
            "APOLLO HOSPITALS, BENGALURU",
            "MEDICAL CERTIFICATE",
            "",
            f"This is to certify that Mr. Rohan Mehta was examined on {d(1):%d %b %Y}",
            "for a ligament injury of the right knee and is advised surgery and rest",
            f"from {d(14):%d %b %Y} to {d(18):%d %b %Y}.",
            "",
            "Dr. Kavita Rao, MBBS, MS (Ortho)  Reg. No. KMC-45821",
        ]
    )
    edited = make_pdf(
        [
            "CITY CARE CLINIC",
            "Medical certificate for Isha Kulkarni",
            f"Advised rest from {d(15):%d %b %Y} to {d(18):%d %b %Y} (viral fever).",
            "Dr. S. Menon",
        ],
        producer="Adobe Photoshop 25.0",
    )
    svc = LeaveService(session)

    # Vikram (HOD) is on approved leave today -> Meera acts for him (delegation demo).
    away = await svc.submit(
        Actor(vikram), from_date=d(0), to_date=d(2), reason="Family function in Mysuru"
    )
    await svc.decide(Actor(arjun), away.id, Action.APPROVE, comment="Enjoy. Meera covers.")

    await svc.submit(
        Actor(sneha), from_date=d(7), to_date=d(8), reason="Sister's engagement in Chennai"
    )
    knee = await svc.submit(
        Actor(rohan),
        from_date=d(14),
        to_date=d(18),
        reason="Knee surgery and recovery",
        uploads=[Upload("medical-certificate.pdf", "application/pdf", cert)],
    )
    await svc.decide(
        Actor(ananya), knee.id, Action.APPROVE, comment="Approved from my side. Cover arranged."
    )
    dev_req = await svc.submit(
        Actor(dev), from_date=d(14), to_date=d(16), reason="Annual family trip"
    )
    await svc.decide(Actor(ananya), dev_req.id, Action.APPROVE, comment="Approved.")
    # Optional doc whose PDF metadata says it went through an image editor.
    await svc.submit(
        Actor(isha),
        from_date=d(15),
        to_date=d(18),
        reason="Viral fever, advised rest",
        uploads=[Upload("clinic-note.pdf", "application/pdf", edited)],
    )
    crew = await svc.submit(
        Actor(tara), from_date=d(3), to_date=d(3), reason="Passport appointment"
    )
    await svc.decide(Actor(meera), crew.id, Action.APPROVE, comment="Fine, swap done with Kabir.")
    # Re-used certificate (the same file as Rohan's) -> verification flags it.
    info = await svc.submit(
        Actor(kabir),
        from_date=d(21),
        to_date=d(25),
        reason="Family emergency back home",
        uploads=[Upload("certificate.pdf", "application/pdf", cert)],
    )
    await svc.decide(
        Actor(meera),
        info.id,
        Action.REQUEST_INFO,
        comment="Can you confirm if you can take the 23rd morning rotation?",
    )
    rej = await svc.submit(Actor(sneha), from_date=d(30), to_date=d(31), reason="Short trip to Goa")
    await svc.decide(
        Actor(ananya),
        rej.id,
        Action.REJECT,
        comment="C-check on VT-AKB is scheduled that week; please pick other dates.",
    )

    # Pre-check every seeded document (offline heuristics; no LLM needed).
    from app.ai.doc_check import analyse

    reqs = (
        await session.scalars(
            select(LeaveRequest).options(
                selectinload(LeaveRequest.employee), selectinload(LeaveRequest.attachments)
            )
        )
    ).all()
    for r in reqs:
        for att in r.attachments:
            await session.refresh(att, ["content"])
            att.ai_check = await analyse(session, att, r, model=None, live=False)
    await session.commit()
    log.info("seeded_demo_data", users=len(people))
    return True
