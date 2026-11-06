"""AI runtime: owns the chat model, the compiled graphs and the checkpointer.

Checkpointer: Postgres in production (pending human confirmations survive restarts); an
in-memory saver for tests/local runs where Postgres async isn't available.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.ai.assistant import build_assistant_graph
from app.ai.copilot import build_copilot_graph
from app.ai.llm import ModelInfo, get_chat_model
from app.core.config import get_settings
from app.core.logging import log


class AIRuntime:
    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self.assistant: Any = None
        self.copilot: Any = None
        self.info: ModelInfo | None = None
        self.model: Any = None
        self.checkpointer_kind = "none"

    async def start(self, *, use_postgres_checkpointer: bool | None = None) -> None:
        settings = get_settings()
        model, self.info = get_chat_model(settings)
        self.model = model
        self._stack = AsyncExitStack()
        if use_postgres_checkpointer is None:
            use_postgres_checkpointer = settings.environment == "production"

        saver: BaseCheckpointSaver[Any]
        if use_postgres_checkpointer:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            saver = await self._stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(settings.psycopg_dsn)
            )
            await saver.setup()  # idempotent: creates checkpoint tables if missing
            self.checkpointer_kind = "postgres"
        else:
            saver = InMemorySaver()
            self.checkpointer_kind = "memory"

        self.assistant = build_assistant_graph(model, saver)
        self.copilot = build_copilot_graph(model)
        log.info(
            "ai_ready",
            provider=self.info.provider,
            model=self.info.model,
            live=self.info.live,
            checkpointer=self.checkpointer_kind,
        )

    async def stop(self) -> None:
        if self._stack:
            await self._stack.aclose()
            self._stack = None


ai_runtime = AIRuntime()
