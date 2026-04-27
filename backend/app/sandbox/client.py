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

    async def list_sessions(self) -> list[SessionInfo]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/sessions")
            response.raise_for_status()
            data = response.json()
        return [
            SessionInfo(
                session_id=item["session_id"],
                status=item["status"],
                container_id=item.get("container_id"),
                vnc_url=f"/vnc/sessions/{item['session_id']}/" if item["status"] != "missing" else None,
            )
            for item in data
        ]

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

    async def capture_action_screenshot(self, session_id: str) -> bytes | None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/sessions/{session_id}/screenshots/action-latest.png"
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.content
