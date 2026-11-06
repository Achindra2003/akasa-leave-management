"""Audit trail writer. Called *inside* the same transaction as the change it records,
so a state change and its audit row commit (or roll back) together."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log, request_id_var
from app.domain.enums import Channel
from app.models import AuditLog


def record(
    session: AsyncSession,
    *,
    actor_id: int | None,
    channel: Channel,
    action: str,
    entity: str,
    entity_id: int | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            channel=channel,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
            meta=meta,
            correlation_id=request_id_var.get(),
        )
    )
    log.info(
        "audit",
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor_id=actor_id,
        channel=channel.value,
    )
