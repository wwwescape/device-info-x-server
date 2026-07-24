#!/bin/sh
set -e

# Bind-mounted host directories aren't auto-chowned by Docker the way a
# named volume is (that only happens once, on first creation, and only
# for volumes) — fix up ownership here, as root, before dropping to the
# unprivileged `app` user. Skipped when already correct so a large media
# library doesn't eat a recursive chown on every restart.
if [ "$(stat -c '%u' /data/media)" != "$(id -u app)" ]; then
  chown -R app:app /data/media
fi

echo "Running database migrations..."
gosu app alembic upgrade head

echo "Starting API server..."
# Must stay 1: the WebSocket connection manager and the in-process rate
# limiter both hold state in-memory with no cross-process pub/sub. Running
# >1 worker would silently split connections/state and break both.
exec gosu app uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-1}"
