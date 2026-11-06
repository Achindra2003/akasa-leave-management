"""Idempotent demo data: a small, fictional airline org that exercises every routing edge
case from DECISIONS.md D-001. All names are fictional; emails use the reserved-style
``.demo`` TLD so nothing can be mistaken for a real mailbox."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.logging import log
from app.core.security import hash_password
from app.domain.enums import Action, Channel, Role
from app.models import Department, User
from app.services.leave_service import Actor, LeaveService, Upload

DEMO_PASSWORD = "Akasa@2026"

# Shown on the login page as one-click sign-ins.
DEMO_ACCOUNTS: list[dict[str, object]] = [
    {
        "name": "Rohan Mehta",
        "email": "rohan@akasa.demo",
        "role": Role.EMPLOYEE,
        "title": "Aircraft Maintenance Engineer",
        "blurb": "Employee. Apply for leave, upload documents, answer info requests.",
    },
    {
        "name": "Ananya Sharma",
        "email": "ananya@akasa.demo",
        "role": Role.MANAGER,
        "title": "Line Maintenance Manager",
        "blurb": "Manager (level 1). Approve, reject or ask for more info.",
    },
    {
        "name": "Vikram Rao",
        "email": "vikram@akasa.demo",
        "role": Role.HOD,
        "title": "Head of Engineering",
        "blurb": "HOD (level 2). Second sign-off for leave longer than 3 days.",
    },
    {
        "name": "Priya Nair",
        "email": "priya@akasa.demo",
        "role": Role.HR_ADMIN,
        "title": "HR Business Partner",
        "blurb": "HR admin. Sees everything, audit log, fallback approver.",
    },
    {
        "name": "Kabir Singh",
        "email": "kabir@akasa.demo",
        "role": Role.EMPLOYEE,
        "title": "Cabin Crew",
        "blurb": "Edge case: his manager is also his HOD, so level 2 routes to HR.",
    },
]

_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


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
    meera = u("Meera Joshi", "meera@akasa.demo", Role.HOD, "Head of In-flight Services")
    kabir = u("Kabir Singh", "kabir@akasa.demo", Role.EMPLOYEE, "Cabin Crew")
    tara = u("Tara Menon", "tara@akasa.demo", Role.EMPLOYEE, "Cabin Crew")
    session.add_all([priya, arjun, vikram, ananya, rohan, sneha, meera, kabir, tara])
    await session.flush()

    for p in (priya, arjun):
        p.department_id = hr_dept.id
    arjun.manager_id = None
    priya.manager_id = arjun.id
    vikram.department_id, vikram.manager_id = eng.id, arjun.id
    ananya.department_id, ananya.manager_id = eng.id, vikram.id
    for e in (rohan, sneha):
        e.department_id, e.manager_id = eng.id, ananya.id
    meera.department_id, meera.manager_id = ifs.id, arjun.id
    for e in (kabir, tara):
        e.department_id, e.manager_id = ifs.id, meera.id  # manager == HOD edge case
    eng.hod_id, ifs.hod_id, hr_dept.hod_id = vikram.id, meera.id, arjun.id
    await session.commit()

    # A few requests so every dashboard has something to show.
    svc = LeaveService(session)
    today = clock.today()

    def d(n: int) -> date:
        return today + timedelta(days=n)

    pdf = [Upload("medical-certificate.pdf", "application/pdf", _PDF)]

    await svc.submit(
        Actor(sneha), from_date=d(7), to_date=d(8), reason="Sister's engagement ceremony in Chennai"
    )
    long_req = await svc.submit(
        Actor(rohan),
        from_date=d(14),
        to_date=d(18),
        reason="Knee surgery and recovery",
        uploads=pdf,
    )
    await svc.decide(
        Actor(ananya),
        long_req.id,
        Action.APPROVE,
        comment="Approved from my side. Roster cover arranged with Sneha.",
    )
    crew = await svc.submit(
        Actor(tara), from_date=d(3), to_date=d(3), reason="Passport appointment"
    )
    await svc.decide(Actor(meera), crew.id, Action.APPROVE, comment="Fine, swap done with Kabir.")
    info = await svc.submit(
        Actor(kabir),
        from_date=d(21),
        to_date=d(25),
        reason="Family emergency back home",
        uploads=pdf,
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
    _ = Channel  # (seed rows are tagged channel=ui by default)
    log.info("seeded_demo_data", users=9)
    return True
