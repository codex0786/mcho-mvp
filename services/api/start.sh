#!/bin/sh
# Container entrypoint for the MCHO API.
# Set RUN_MIGRATIONS_ON_START=1 on hosts without a pre-deploy step (e.g. Render's
# free plan) to apply Alembic migrations before serving. Leave it unset where
# migrations run separately (Docker Compose, the paid Render pilot).
set -eu

if [ "${RUN_MIGRATIONS_ON_START:-0}" = "1" ]; then
  echo "Applying database migrations before start..."
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
