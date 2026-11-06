import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.core.compat import use_compatible_event_loop
from app.core.config import get_settings
from app.core.db import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Tables owned by LangGraph's checkpointer (created by saver.setup()), not by our models.
# Without this, autogenerate would emit DROP TABLE for them.
_EXTERNAL_TABLES = {"checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations"}


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table not in _EXTERNAL_TABLES


def _url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    use_compatible_event_loop()
    asyncio.run(run_async_migrations())
