"""Test harness.

Integration tests run against a real Postgres (the exclusion constraint, row versioning
and append-only trigger are Postgres features - D-013). Point TEST_DATABASE_URL at any
Postgres; by default we use a ``leave_test`` database on the docker-compose ``db``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://leave:leave@localhost:5432/leave_test"
)
os.environ.update(
    DATABASE_URL=TEST_DB,
    ENVIRONMENT="test",
    SEED_DEMO_DATA="false",
    LLM_PROVIDER="fake",
    LOG_LEVEL="WARNING",
)


if sys.platform == "win32":  # psycopg async can't use the Proactor loop (app/core/compat.py)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]


def _ensure_database() -> None:
    import psycopg

    base, _, name = TEST_DB.replace("postgresql+psycopg://", "postgresql://").rpartition("/")
    with psycopg.connect(f"{base}/postgres", autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{name}"')


def _migrate() -> None:
    from alembic.config import Config

    from alembic import command

    here = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "alembic"))
    cfg.attributes["database_url"] = TEST_DB
    cfg.attributes["skip_logging"] = True
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def migrated_db() -> None:
    try:
        _ensure_database()
    except Exception as e:  # pragma: no cover
        pytest.skip(
            f"Postgres not reachable for integration tests ({e}). Run: docker compose up -d db"
        )
    _migrate()


@pytest.fixture(scope="session")
async def app(migrated_db: None) -> AsyncIterator[object]:
    from asgi_lifespan import LifespanManager

    from app.main import create_app

    application = create_app()
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def _clean(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    if "app" not in request.fixturenames:
        yield
        return
    from app.core.hardening import ai_limiter, login_limiter

    login_limiter.reset()
    ai_limiter.reset()
    from sqlalchemy import text

    from app.core.db import get_engine

    async with get_engine().begin() as conn:
        # TRUNCATE doesn't fire the row-level append-only trigger.
        await conn.execute(
            text(
                "TRUNCATE notifications, blackout_periods, agent_runs, audit_logs, comments, "
                "attachments, approval_steps, "
                "leave_requests, departments, users RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture
async def client(app: object) -> AsyncIterator[object]:
    import httpx

    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@dataclass
class Org:
    """Engineering: emp & peer -> mgr -> hod(HOD).  Crew: crew -> lead (manager AND HOD).
    HR: hr, hr2.  ``outsider`` is unrelated to everyone."""

    ids: dict[str, int]
    tokens: dict[str, str]

    def h(self, who: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[who]}"}


PASSWORD = "Test@12345"


@pytest.fixture
async def org(app: object) -> Org:
    from app.core.db import get_sessionmaker
    from app.core.security import create_access_token, hash_password
    from app.domain.enums import Role
    from app.models import Department, User

    pw = hash_password(PASSWORD)
    async with get_sessionmaker()() as s:
        eng, crew_d, other = Department(name="Eng"), Department(name="Crew"), Department(name="X")
        s.add_all([eng, crew_d, other])
        await s.flush()
        spec = {
            "hr": Role.HR_ADMIN,
            "hr2": Role.HR_ADMIN,
            "hod": Role.HOD,
            "mgr": Role.MANAGER,
            "emp": Role.EMPLOYEE,
            "peer": Role.EMPLOYEE,
            "lead": Role.HOD,
            "crew": Role.EMPLOYEE,
            "outsider": Role.EMPLOYEE,
        }
        users = {
            k: User(name=k.title(), email=f"{k}@t.demo", role=r, password_hash=pw)
            for k, r in spec.items()
        }
        s.add_all(users.values())
        await s.flush()
        u = users
        u["hod"].department_id = eng.id
        u["mgr"].department_id, u["mgr"].manager_id = eng.id, u["hod"].id
        for k in ("emp", "peer"):
            u[k].department_id, u[k].manager_id = eng.id, u["mgr"].id
        u["lead"].department_id = crew_d.id
        u["crew"].department_id, u["crew"].manager_id = crew_d.id, u["lead"].id
        u["outsider"].department_id = other.id
        u["outsider"].manager_id = u["hr"].id
        eng.hod_id, crew_d.hod_id = u["hod"].id, u["lead"].id
        await s.commit()
        ids = {k: v.id for k, v in users.items()}
        tokens = {k: create_access_token(v.id, v.role.value) for k, v in users.items()}
    return Org(ids, tokens)
