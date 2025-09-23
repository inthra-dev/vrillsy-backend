# Reels Generator (FastAPI + Celery + Next.js + Redis)

## Struktura
- backend/ — FastAPI (uvicorn)
- worker/ — Celery worker
- frontend/ — Next.js (prod)
- shared/ — moduł współdzielony (zadania Celery)
- outputs/ — artefakty zadań

## Uruchomienie
# Docker Compose v2 (preferowane):
docker compose up --build -d

# Jeśli masz starsze narzędzia:
docker-compose up --build -d

## Zatrzymanie
docker compose down -v || docker-compose down -v

## Endpointy
- Frontend: http://localhost:${FRONTEND_PORT:-3000}
- Backend (sieć wewnętrzna): http://backend:8000  (z frontu)
  - Health: GET /ping
  - Celery: POST /task/add {"x":2,"y":3}, GET /task/{id}

## Zmienne środowiskowe (.env)
- BACKEND_PORT=8000
- FRONTEND_PORT=3000
- REDIS_URL=redis://redis:6379/0
- CELERY_BROKER_URL=${REDIS_URL}
- CELERY_RESULT_BACKEND=${REDIS_URL}
- OUTPUT_DIR=/data/outputs
- FRONTEND_ORIGIN=http://localhost:3000
- NEXT_PUBLIC_BACKEND_URL=http://backend:8000
