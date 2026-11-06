"""Typed configuration from environment variables (12-factor). See .env.example."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.policy import LeavePolicy


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Akasa Leave"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = "postgresql+psycopg://leave:leave@localhost:5432/leave"
    # Pool sized to the database plan (D-025): Supabase's session pooler allows 15 clients
    # per database on the free tier, shared by every app instance + the checkpointer.
    db_pool_size: int = 4
    db_max_overflow: int = 4
    db_pool_timeout_s: float = 10.0  # bursts queue for a connection instead of failing

    jwt_secret: str = Field(default="dev-only-change-me-please-32bytes!!", min_length=32)
    jwt_ttl_minutes: int = 8 * 60
    cors_origins: list[str] = ["http://localhost:5173"]  # SPA is same-origin in prod

    seed_demo_data: bool = True
    # "Today" is evaluated in the organisation's timezone, not UTC (an IST user applying at
    # 00:30 must not be told their leave starts in the past).
    app_timezone: str = "Asia/Kolkata"
    serve_frontend_dir: str | None = None  # path to built SPA (set in Docker)

    # Policy (D-002): data, not code
    leave_escalation_threshold_days: int = 3
    leave_max_span_days: int = 30
    max_upload_mb: int = 5
    # Coverage (D-021): at least this share of a team must be available on any day.
    min_team_available_ratio: float = 0.5

    # AI (D-012): provider-agnostic. "fake" = deterministic, offline, no key needed.
    llm_provider: Literal["groq", "openai_compat", "fake"] = "fake"
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_temperature: float = 0.0
    llm_timeout_s: float = 30.0
    agent_max_steps: int = 8

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Render/Neon hand out postgres:// URLs; SQLAlchemy needs the driver suffix.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @property
    def psycopg_dsn(self) -> str:
        """Plain libpq DSN for the LangGraph Postgres checkpointer."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")

    @property
    def policy(self) -> LeavePolicy:
        return LeavePolicy(
            escalation_threshold_days=self.leave_escalation_threshold_days,
            max_span_days=self.leave_max_span_days,
            max_document_bytes=self.max_upload_mb * 1024 * 1024,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
