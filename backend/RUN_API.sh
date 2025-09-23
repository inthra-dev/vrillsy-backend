#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export VRS_DISABLE_AUTH="${VRS_DISABLE_AUTH:-1}"
# broker/backend też na localhost (spójnie z workerem)
export VRS_CELERY_BROKER_URL="${VRS_CELERY_BROKER_URL:-redis://127.0.0.1:6379/0}"
export VRS_CELERY_BACKEND_URL="${VRS_CELERY_BACKEND_URL:-redis://127.0.0.1:6379/1}"

# wybierz pierwszy wolny port 8000-8010
for p in $(seq 8000 8010); do
  if ! ss -ltn | awk '{print $4}' | grep -q ":$p$"; then PORT="$p"; break; fi
done
[ -n "$PORT" ] || { echo "[FAIL] Brak wolnego portu 8000-8010"; exit 1; }

echo "[INFO] API port: $PORT  |  VRS_DISABLE_AUTH=$VRS_DISABLE_AUTH"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
