"""Platform shims.

psycopg's async mode can't run on Windows' default ProactorEventLoop. Production runs
on Linux (Docker), but local dev on Windows should work too, so we switch policy there.
"""

import asyncio
import sys


def use_compatible_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
