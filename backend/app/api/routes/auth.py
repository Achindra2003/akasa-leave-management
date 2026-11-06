from fastapi import APIRouter
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.api.presenters import user_out
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.domain.enums import Channel, Role
from app.domain.errors import AuthenticationFailed, NotFound
from app.models import Department, User
from app.schemas import DemoAccount, LoginIn, TokenOut, UserOut
from app.seed import DEMO_ACCOUNTS, DEMO_PASSWORD
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


async def _is_approver(session: SessionDep, user: User) -> bool:
    if user.role in (Role.HR_ADMIN, Role.HOD, Role.MANAGER):
        return True
    q = select(
        or_(
            exists().where(User.manager_id == user.id),
            exists().where(Department.hod_id == user.id),
        )
    )
    return bool(await session.scalar(q))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: SessionDep) -> TokenOut:
    user = await session.scalar(
        select(User)
        .options(selectinload(User.department), selectinload(User.manager))
        .where(User.email == body.email.lower())
    )
    if user is None or not verify_password(body.password, user.password_hash):
        raise AuthenticationFailed("That email and password don't match. Please try again.")
    audit.record(
        session,
        actor_id=user.id,
        channel=Channel.UI,
        action="auth.login",
        entity="user",
        entity_id=user.id,
    )
    await session.commit()
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value),
        user=user_out(user, is_approver=await _is_approver(session, user)),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser, session: SessionDep) -> UserOut:
    return user_out(user, is_approver=await _is_approver(session, user))


@router.get("/demo-accounts", response_model=list[DemoAccount])
async def demo_accounts() -> list[DemoAccount]:
    """One-click demo logins for assessors. Disabled when demo data isn't seeded."""
    if not get_settings().seed_demo_data:
        raise NotFound("Demo accounts are disabled.")
    return [DemoAccount(**a, password=DEMO_PASSWORD) for a in DEMO_ACCOUNTS]
