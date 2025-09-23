from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
import os

try:
    # użyj istniejącej aplikacji
    from app.main import app  # type: ignore
except Exception:
    app = FastAPI(title="Vrillsy API (fallback)")

class Health(BaseModel):
    status: str
    env: str | None = None

router = APIRouter()

@router.get("/health", response_model=Health)
def health():
    return Health(status="ok", env=os.getenv("ENV","dev"))

app.include_router(router)
