from __future__ import annotations

import asyncio
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
from app.llm.function_computer import parse_function_response
from app.llm.prompts import (
    action_feedback_payload,
    screen_feedback_text,
    system_instructions,
)
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
        history.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            action_feedback_payload(
                                previous=previous,
                                action_results=action_results,
                                screenshot=screenshot,
                            )
                        ),
                    }
                ],
            }
        )
        screenshot_content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": screen_feedback_text(
                    previous=previous,
                    action_results=action_results,
                    screenshot=screenshot,
                ),
            }
        ]
        if self._settings.llm_supports_vision:
            screenshot_content.append({"type": "input_image", "image_url": screenshot.data_url})
        history.append({"role": "user", "content": screenshot_content})
        return await self._send(session_id)

    async def _send(self, session_id: str) -> AgentResponse:
        history = self._history[session_id]
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "instructions": system_instructions(self._settings, native_computer=False),
            "tools": [
                function_tool_schema(
                    display_width=self._settings.display_width,
                    display_height=self._settings.display_height,
                )
            ],
            "tool_choice": "auto",
            "input": list(history),
        }
        response = await self._post_responses_with_retry(body)
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

    async def _post_responses_with_retry(self, body: dict[str, Any]) -> httpx.Response:
        last_exc: httpx.ReadTimeout | None = None
        for attempt in range(2):
            try:
                return await self._client.post("/responses", json=body)
            except httpx.ReadTimeout as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
        raise RuntimeError("Responses request timed out after retry") from last_exc
