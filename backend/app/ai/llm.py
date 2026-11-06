"""Model-agnostic chat model factory (DECISIONS.md D-012).

Graphs depend only on LangChain's ``BaseChatModel`` interface, so switching provider is a
config change:

    LLM_PROVIDER=groq           LLM_MODEL=openai/gpt-oss-120b          LLM_API_KEY=gsk_...
    LLM_PROVIDER=openai_compat  LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-...
    LLM_PROVIDER=openai_compat  LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=llama3.1  (Ollama)
    LLM_PROVIDER=fake           (deterministic, offline - tests, evals, keyless demo)
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from app.core.config import Settings
from app.core.logging import log


@dataclass(frozen=True, slots=True)
class ModelInfo:
    provider: str
    model: str
    live: bool  # False => deterministic demo model


def get_chat_model(settings: Settings) -> tuple[BaseChatModel, ModelInfo]:
    provider = settings.llm_provider
    if provider != "fake" and not settings.llm_api_key and provider != "openai_compat":
        # Fail soft: the portal must work without AI credentials (graceful degradation).
        log.warning("llm_key_missing_falling_back_to_demo_model", provider=provider)
        provider = "fake"

    if provider == "groq":
        from langchain_groq import ChatGroq

        return (
            ChatGroq(
                model=settings.llm_model,
                api_key=settings.llm_api_key,  # type: ignore[arg-type]
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_s,
                max_retries=2,
            ),
            ModelInfo("groq", settings.llm_model, True),
        )
    if provider == "openai_compat":
        from langchain_openai import ChatOpenAI

        return (
            ChatOpenAI(
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key or "not-needed",  # type: ignore[arg-type]
                temperature=settings.llm_temperature,
                timeout=settings.llm_timeout_s,
                max_retries=2,
            ),
            ModelInfo("openai_compat", settings.llm_model, True),
        )

    from app.ai.fake_model import ScriptedLeaveModel

    return ScriptedLeaveModel(), ModelInfo("fake", "scripted-demo-model", False)
