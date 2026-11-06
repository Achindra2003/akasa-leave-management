#!/bin/sh
# Apply migrations, then serve. Migrations are idempotent; with >1 replica, run them as a
# separate release step instead (see docs/DECISIONS.md D-014).
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers \
  --forwarded-allow-ips='*' --workers "${WEB_CONCURRENCY:-1}"
