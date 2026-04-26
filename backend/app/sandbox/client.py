import uuid

import httpx

from app.config import Settings
from app.schemas.sessions import CommandSmokeResult, SessionInfo


class SandboxClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.sandbox_controller_url.rstrip("/")

    async def create_session(self, requested_session_id: str | None = None) -> SessionInfo:
        session_id = requested_session_id or uuid.uuid4().hex
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self._base_url}/sessions", json={"session_id": session_id})
            response.raise_for_status()
            data = response.json()
        return SessionInfo(
            session_id=data["session_id"],
            status=data["status"],
            container_id=data.get("container_id"),
            vnc_url=f"/vnc/sessions/{data['session_id']}/",
        )

    async def get_session(self, session_id: str) -> SessionInfo:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/sessions/{session_id}")
            response.raise_for_status()
            data = response.json()
        return SessionInfo(
            session_id=data["session_id"],
            status=data["status"],
            container_id=data.get("container_id"),
            vnc_url=f"/vnc/sessions/{data['session_id']}/" if data["status"] != "missing" else None,
        )

    async def delete_session(self, session_id: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(f"{self._base_url}/sessions/{session_id}")
            response.raise_for_status()

    async def run_smoke_command(self, session_id: str, operation: str) -> CommandSmokeResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/sessions/{session_id}/commands",
                json={"operation": operation},
            )
            response.raise_for_status()
            data = response.json()
        return CommandSmokeResult(**data)

    async def capture_screenshot(self, session_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self._base_url}/sessions/{session_id}/screenshots/latest.png")
            response.raise_for_status()
            return response.content
