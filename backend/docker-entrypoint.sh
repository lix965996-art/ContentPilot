#!/bin/sh
set -eu

echo "[ContentPilot] Applying database migrations..."
python -m alembic upgrade head

echo "[ContentPilot] Seeding required roles and initial data..."
python -m app.db.seed

echo "[ContentPilot] Starting API..."
exec "$@"
