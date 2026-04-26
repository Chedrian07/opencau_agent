from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import Settings
from app.llm.base import ActionResult
from app.schemas.actions import Action, ActionValidationError, ensure_within_display


class ActionExecutor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.sandbox_controller_url.rstrip("/")

    async def execute(
        self,
        *,
        session_id: str,
        action: Action,
        client: httpx.AsyncClient | None = None,
    ) -> ActionResult:
        try:
            ensure_within_display(
                action,
                width=self._settings.display_width,
                height=self._settings.display_height,
            )
        except ActionValidationError as exc:
            return ActionResult(
                action=action,
                status="error",
                duration_ms=0,
                error_code="ACTION_OUT_OF_BOUNDS",
                message=str(exc),
            )
        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=self._settings.action_timeout_sec + 5)
        started = time.monotonic()
        try:
            response = await http.post(
                f"{self._base_url}/sessions/{session_id}/actions",
                json=action.model_dump(exclude_none=True),
                timeout=self._settings.action_timeout_sec + 5,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            duration_ms = int(data.get("duration_ms", (time.monotonic() - started) * 1000))
            status = data.get("status", "error")
            return ActionResult(
                action=action,
                status="ok" if status == "ok" else "error",
                duration_ms=max(duration_ms, 0),
                output=data.get("output", "") or "",
                error_code=data.get("error_code"),
                message=data.get("message"),
            )
        except httpx.HTTPStatusError as exc:
            return ActionResult(
                action=action,
                status="error",
                duration_ms=int((time.monotonic() - started) * 1000),
                error_code="SANDBOX_HTTP_ERROR",
                message=f"{exc.response.status_code}: {exc.response.text[:300]}",
            )
        except httpx.HTTPError as exc:
            return ActionResult(
                action=action,
                status="error",
                duration_ms=int((time.monotonic() - started) * 1000),
                error_code="SANDBOX_TRANSPORT_ERROR",
                message=str(exc),
            )
        finally:
            if owns_client:
                await http.aclose()
