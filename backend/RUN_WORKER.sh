#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

# Redis przez podman (idempotentnie)
if ! podman ps --format '{{.Names}}' | grep -q '^vrillsy-redis$'; then
  podman rm -f vrillsy-redis >/dev/null 2>&1 || true
  podman run -d --name vrillsy-redis -p 6379:6379 docker.io/redis:7-alpine >/dev/null
fi

# Wymuś lokalny Redis (localhost zamiast 'redis')
export VRS_CELERY_BROKER_URL="${VRS_CELERY_BROKER_URL:-redis://127.0.0.1:6379/0}"
export VRS_CELERY_BACKEND_URL="${VRS_CELERY_BACKEND_URL:-redis://127.0.0.1:6379/1}"

echo "[INFO] Broker:  $VRS_CELERY_BROKER_URL"
echo "[INFO] Backend: $VRS_CELERY_BACKEND_URL"
exec celery -A app.celeryapp.celery_app worker -l info
