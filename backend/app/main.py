from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events, health, preflight, sessions, vnc_proxy
from app.config import get_settings


app = FastAPI(title="OpenCAU Agent Backend", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["content-type"],
)

app.include_router(health.router, prefix="/api")
app.include_router(preflight.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(events.ws_router)
app.include_router(vnc_proxy.router)
