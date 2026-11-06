"""In-app notifications.

Written in the same transaction as the event that caused them, so a notification never
refers to a change that rolled back. This table is also the single hook point for
email/Slack later: an outbox worker would read it and deliver.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification


async def notify(
    session: AsyncSession,
    user_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    request_id: int | None = None,
) -> None:
    session.add(
        Notification(
            user_id=user_id, kind=kind, title=title[:200], body=body, request_id=request_id
        )
    )
