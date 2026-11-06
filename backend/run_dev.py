"""Local dev server (handles the Windows event-loop quirk, see app/core/compat.py)."""

import uvicorn

from app.core.compat import use_compatible_event_loop

if __name__ == "__main__":
    use_compatible_event_loop()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False, loop="none")
