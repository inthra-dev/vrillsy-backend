import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from .routers.generate import router as generate_router
from .routers.status import router as status_router

app = FastAPI(title="Vrillsy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN","http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_current_user():
    if os.getenv('VRS_DISABLE_AUTH','').lower() in {'1','true','yes'}:
        return {'sub':'dev'}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Unauthorized')

@app.get("/health")
def health():
    return {"ok": True}

app.include_router(generate_router, dependencies=[Depends(get_current_user)])
app.include_router(status_router, dependencies=[Depends(get_current_user)])
