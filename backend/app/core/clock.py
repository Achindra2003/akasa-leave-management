"""Organisation-local clock. Single source of "today" for validation and the AI agent."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().app_timezone))


def today() -> date:
    return now().date()
