"""FastAPI dependencies: DB session, current user, role guards, services."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import decode_access_token
from app.domain.enums import Role
from app.domain.errors import AuthenticationFailed, Forbidden
from app.models import User
from app.services.leave_service import LeaveService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if creds is None:
        raise AuthenticationFailed("Please sign in to continue.")
    user_id = decode_access_token(creds.credentials)
    user = await session.scalar(
        select(User)
        .options(
            joinedload(User.department),
            joinedload(User.manager),
            joinedload(User.delegate),
        )
        .where(User.id == user_id)
    )
    if user is None:
        raise AuthenticationFailed("Your account no longer exists. Please sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):  # type: ignore[no-untyped-def]
    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise Forbidden("This area is only available to " + ", ".join(r.value for r in roles))
        return user

    return _guard


HRUser = Annotated[User, Depends(require_roles(Role.HR_ADMIN))]


def get_leave_service(session: SessionDep) -> LeaveService:
    return LeaveService(session, policy=get_settings().policy)


LeaveServiceDep = Annotated[LeaveService, Depends(get_leave_service)]
