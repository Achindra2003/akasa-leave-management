"""AI endpoints: employee assistant (agent + human confirmation) and approver co-pilot."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from pydantic import Field

from app.ai.copilot import gather_facts
from app.ai.runtime import ai_runtime
from app.api.deps import CurrentUser, LeaveServiceDep, SessionDep
from app.core import clock
from app.core.config import get_settings
from app.core.hardening import ai_limiter
from app.core.logging import log
from app.domain.enums import Role
from app.domain.errors import DomainError, Forbidden, NotFound
from app.models import AgentRun, User
from app.schemas import ApiModel

router = APIRouter(prefix="/ai", tags=["ai"])


class AIStatus(ApiModel):
    provider: str
    model: str
    live: bool
    checkpointer: str


class ChatIn(ApiModel):
    message: str = Field(min_length=1, max_length=1000)
    thread_id: str | None = None


class ConfirmIn(ApiModel):
    thread_id: str
    approve: bool


class ChatOut(ApiModel):
    thread_id: str
    reply: str
    draft: dict[str, Any] | None = None
    awaiting_confirmation: bool = False
    submitted_request_id: int | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    live_model: bool


class CopilotOut(ApiModel):
    summary: str
    flags: list[dict[str, str]]
    suggested_questions: list[str]
    recommendation: str
    facts: dict[str, Any]
    live_model: bool


class AIUnavailable(DomainError):
    status_code = 503
    code = "ai_unavailable"
    title = "Assistant unavailable"


@router.get("/status", response_model=AIStatus)
async def status() -> AIStatus:
    info = ai_runtime.info
    return AIStatus(
        provider=info.provider if info else "none",
        model=info.model if info else "none",
        live=bool(info and info.live),
        checkpointer=ai_runtime.checkpointer_kind,
    )


def _config(user: User, thread_id: str) -> dict[str, Any]:
    s = get_settings()
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user.id,  # tools act as this user - never taken from model output
            "user_name": user.name,
            "user_title": user.title,
            "today": clock.now().isoformat(),
        },
        "recursion_limit": s.agent_max_steps * 2 + 2,  # each step = agent + tools node
    }


def _own_thread(user: User, thread_id: str | None) -> str:
    if thread_id is None:
        return f"u{user.id}-{uuid.uuid4().hex[:16]}"
    if not thread_id.startswith(f"u{user.id}-"):
        raise Forbidden("That conversation belongs to someone else.")
    return thread_id


def _trace(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                steps.append({"type": "tool_call", "tool": tc["name"], "args": tc["args"]})
        elif isinstance(m, ToolMessage):
            steps.append({"type": "tool_result", "tool": m.name, "content": str(m.content)[:500]})
    return steps


async def _run(
    session: SessionDep, user: User, thread_id: str, graph_input: Any, label: str
) -> ChatOut:
    if ai_runtime.assistant is None or ai_runtime.info is None:
        raise AIUnavailable("The assistant isn't available right now. The portal works as usual.")
    cfg = _config(user, thread_id)
    before = await ai_runtime.assistant.aget_state(cfg)
    n_before = len(before.values.get("messages", [])) if before.values else 0
    started = time.perf_counter()
    error = None
    try:
        await ai_runtime.assistant.ainvoke(graph_input, cfg)
    except GraphRecursionError:
        error = "step_limit"
    except Exception as e:  # provider outage, timeout... -> fail soft, keep portal usable
        log.exception("assistant_failed", error=repr(e))
        error = type(e).__name__

    state = await ai_runtime.assistant.aget_state(cfg)
    values = state.values or {}
    new_msgs = values.get("messages", [])[n_before:]
    interrupts = getattr(state, "interrupts", ()) or ()
    pending = next((i.value for i in interrupts if isinstance(i.value, dict)), None)
    last_ai = next((m for m in reversed(new_msgs) if isinstance(m, AIMessage) and m.content), None)

    if error == "step_limit":
        reply = "Sorry, I got stuck on that one. Could you rephrase it with the exact dates?"
    elif error:
        reply = "The assistant is having trouble reaching the AI service. Please use the form."
    elif pending:
        reply = "Here's your draft. Please review it and confirm to submit."
    else:
        reply = str(last_ai.content) if last_ai else "Okay."

    draft = pending["draft"] if pending else values.get("draft")
    steps = _trace(new_msgs)
    session.add(
        AgentRun(
            user_id=user.id,
            kind="assistant",
            thread_id=thread_id,
            input=label[:1000],
            output=reply[:2000],
            steps=steps,
            provider=ai_runtime.info.provider,
            model=ai_runtime.info.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=error,
        )
    )
    await session.commit()
    return ChatOut(
        thread_id=thread_id,
        reply=reply,
        draft=draft,
        awaiting_confirmation=pending is not None,
        submitted_request_id=values.get("submitted_request_id") if not pending else None,
        steps=steps,
        live_model=ai_runtime.info.live,
    )


@router.post("/assistant/chat", response_model=ChatOut)
async def chat(body: ChatIn, user: CurrentUser, session: SessionDep) -> ChatOut:
    ai_limiter.check(f"user:{user.id}")
    thread_id = _own_thread(user, body.thread_id)
    cfg = _config(user, thread_id)
    if ai_runtime.assistant is not None:
        st = await ai_runtime.assistant.aget_state(cfg)
        if getattr(st, "interrupts", None):  # new message while a draft awaits -> discard it
            await ai_runtime.assistant.ainvoke(Command(resume={"approve": False}), cfg)
    return await _run(
        session,
        user,
        thread_id,
        {"messages": [HumanMessage(body.message)], "submitted_request_id": None},
        body.message,
    )


@router.post("/assistant/confirm", response_model=ChatOut)
async def confirm(body: ConfirmIn, user: CurrentUser, session: SessionDep) -> ChatOut:
    ai_limiter.check(f"user:{user.id}")
    """Resume the paused graph with the human's decision (approve -> submit)."""
    thread_id = _own_thread(user, body.thread_id)
    if ai_runtime.assistant is None:
        raise AIUnavailable("The assistant isn't available right now.")
    st = await ai_runtime.assistant.aget_state(_config(user, thread_id))
    if not getattr(st, "interrupts", None):
        raise NotFound("There's no draft waiting for confirmation in this conversation.")
    return await _run(
        session,
        user,
        thread_id,
        Command(resume={"approve": body.approve}),
        f"[confirm approve={body.approve}]",
    )


@router.get("/copilot/{request_id}", response_model=CopilotOut)
async def copilot(
    request_id: int, user: CurrentUser, svc: LeaveServiceDep, session: SessionDep
) -> CopilotOut:
    ai_limiter.check(f"user:{user.id}")
    req = await svc.get(request_id, user)
    acting = await svc.acting_for(user)
    is_approver = any(
        s.approver_id == user.id or s.approver_id in acting or s.acted_by_id == user.id
        for s in req.steps
    )
    if not (is_approver or user.role is Role.HR_ADMIN) or req.employee_id == user.id:
        raise Forbidden("The review co-pilot is available to approvers only.")
    facts = await gather_facts(svc, req)
    if ai_runtime.copilot is None or ai_runtime.info is None:
        raise AIUnavailable("The co-pilot isn't available right now.")

    started = time.perf_counter()
    error = None
    try:
        out = await ai_runtime.copilot.ainvoke({"request_id": request_id, "facts": facts})
        brief = out["brief"]
    except Exception as e:
        from app.ai.copilot import fallback_brief

        log.exception("copilot_failed", error=repr(e))
        error, brief = type(e).__name__, fallback_brief(facts)
    session.add(
        AgentRun(
            user_id=user.id,
            kind="copilot",
            thread_id=None,
            input=f"request:{request_id}",
            output=brief["summary"],
            steps=[{"type": "facts", "content": facts}],
            provider=ai_runtime.info.provider,
            model=ai_runtime.info.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=error,
        )
    )
    await session.commit()
    return CopilotOut(
        summary=brief["summary"],
        flags=brief["flags"],
        suggested_questions=brief.get("suggestedQuestions", []),
        recommendation=brief["recommendation"],
        facts=facts,
        live_model=ai_runtime.info.live and error is None,
    )
