from __future__ import annotations

import json
from collections import deque
from typing import Any

import httpx

from app.config import Settings
from app.llm.base import (
    ActionResult,
    AdapterCapability,
    AgentResponse,
    Screenshot,
)
from app.llm.function_computer import SYSTEM_INSTRUCTIONS, parse_function_response
from app.llm.tool_schema import function_tool_schema


class StatelessFunctionAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=settings.llm_request_timeout_sec,
            headers={
                "authorization": f"Bearer {settings.llm_api_key or 'placeholder'}",
                "content-type": "application/json",
            },
        )
        self.capability = AdapterCapability(
            profile=settings.llm_profile,
            tool_mode=settings.llm_tool_mode,
            state_mode=settings.llm_state_mode,
            supports_vision=settings.llm_supports_vision,
            supports_tool_calls=settings.llm_supports_tool_calls,
            supports_native_computer=False,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
        self._history.clear()

    async def create_initial_response(
        self,
        *,
        session_id: str,
        user_message: str,
        screenshot: Screenshot | None,
    ) -> AgentResponse:
        history = self._history.setdefault(
            session_id,
            deque(maxlen=self._settings.llm_history_window),
        )
        history.clear()
        content: list[dict[str, Any]] = [{"type": "input_text", "text": user_message}]
        if screenshot is not None and self._settings.llm_supports_vision:
            content.append({"type": "input_image", "image_url": screenshot.data_url})
        history.append({"role": "user", "content": content})
        return await self._send(session_id)

    async def continue_after_actions(
        self,
        *,
        previous: AgentResponse,
        action_results: list[ActionResult],
        screenshot: Screenshot,
    ) -> AgentResponse:
        session_id = previous.extra.get("__session_id") if previous.extra else None
        if not isinstance(session_id, str):
            raise RuntimeError("stateless adapter requires session id in previous response extra")
        history = self._history.setdefault(
            session_id,
            deque(maxlen=self._settings.llm_history_window),
        )
        executed = [
            {
                "type": result.action.type,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "error_code": result.error_code,
            }
            for result in action_results
        ]
        history.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"executed_actions": executed}),
                    }
                ],
            }
        )
        screenshot_content: list[dict[str, Any]] = [
            {"type": "input_text", "text": "Updated screenshot after the computer actions."}
        ]
        if self._settings.llm_supports_vision:
            screenshot_content.append({"type": "input_image", "image_url": screenshot.data_url})
        history.append({"role": "user", "content": screenshot_content})
        return await self._send(session_id)

    async def _send(self, session_id: str) -> AgentResponse:
        history = self._history[session_id]
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "instructions": SYSTEM_INSTRUCTIONS,
            "tools": [
                function_tool_schema(
                    display_width=self._settings.display_width,
                    display_height=self._settings.display_height,
                )
            ],
            "tool_choice": "auto",
            "input": list(history),
        }
        response = await self._client.post("/responses", json=body)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Responses error {response.status_code}: {response.text[:1000]}"
            )
        parsed = parse_function_response(
            response.json(),
            display_width=self._settings.display_width,
            display_height=self._settings.display_height,
        )
        parsed.extra = {**parsed.extra, "__session_id": session_id}
        return parsed
