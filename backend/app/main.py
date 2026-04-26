from fastapi import FastAPI

from app.api import health, sessions, vnc_proxy


app = FastAPI(title="OpenCAU Agent Backend", version="0.1.0")

app.include_router(health.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(vnc_proxy.router)
