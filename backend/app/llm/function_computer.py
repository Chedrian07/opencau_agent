from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings
from app.llm.base import (
    ActionResult,
    AdapterCapability,
    AgentResponse,
    Screenshot,
)
from app.llm.normalize import normalize_actions
from app.llm.tool_schema import function_tool_schema


SYSTEM_INSTRUCTIONS = (
    "You operate a remote Ubuntu desktop via the 'computer' function tool. "
    "Each call must include an actions array. Inspect the most recent screenshot "
    "before deciding the next call. Use Korean for reasoning summaries and final "
    "answers when appropriate. Do not open terminals or use shell workflows; rely "
    "on normal GUI/browser actions. Click the visual center of targets, especially "
    "desktop launchers, instead of their label or top-left edge. If the screen is "
    "unchanged after an action, choose a different target or coordinate rather than "
    "repeating the same action. The desktop provides a Firefox launcher when browser "
    "navigation is needed. Finish without calling the tool when the task is done."
)


class FunctionComputerAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
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

    async def create_initial_response(
        self,
        *,
        session_id: str,
        user_message: str,
        screenshot: Screenshot | None,
    ) -> AgentResponse:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": user_message}]
        if screenshot is not None and self._settings.llm_supports_vision:
            content.append({"type": "input_image", "image_url": screenshot.data_url})
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
            "input": [{"role": "user", "content": content}],
        }
        return await self._send(body)

    async def continue_after_actions(
        self,
        *,
        previous: AgentResponse,
        action_results: list[ActionResult],
        screenshot: Screenshot,
    ) -> AgentResponse:
        if previous.raw_call_id is None:
            raise RuntimeError("previous response has no function_call id")
        executed = [
            {
                "type": result.action.type,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "error_code": result.error_code,
            }
            for result in action_results
        ]
        screenshot_msg = (
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Updated screenshot after the computer actions."},
                        {"type": "input_image", "image_url": screenshot.data_url},
                    ],
                }
            ]
            if self._settings.llm_supports_vision
            else []
        )
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "previous_response_id": previous.response_id,
            "tools": [
                function_tool_schema(
                    display_width=self._settings.display_width,
                    display_height=self._settings.display_height,
                )
            ],
            "tool_choice": "auto",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": previous.raw_call_id,
                    "output": json.dumps(
                        {
                            "status": "ok" if all(r.status == "ok" for r in action_results) else "partial",
                            "executed_actions": executed,
                        }
                    ),
                },
                *screenshot_msg,
            ],
        }
        return await self._send(body)

    async def _send(self, body: dict[str, Any]) -> AgentResponse:
        response = await self._client.post("/responses", json=body)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Responses error {response.status_code}: {response.text[:1000]}"
            )
        data = response.json()
        return parse_function_response(
            data,
            display_width=self._settings.display_width,
            display_height=self._settings.display_height,
        )


def parse_function_response(
    data: dict[str, Any],
    *,
    display_width: int | None = None,
    display_height: int | None = None,
) -> AgentResponse:
    output = data.get("output") or []
    actions_payload: list[dict[str, Any]] = []
    raw_call_id: str | None = None
    text_parts: list[str] = []
    summary_parts: list[str] = []
    for item in output:
        item_type = item.get("type")
        if item_type in {"function_call", "tool_call"}:
            raw_call_id = item.get("call_id") or item.get("id")
            arguments = item.get("arguments")
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError:
                    parsed = {}
            elif isinstance(arguments, dict):
                parsed = arguments
            else:
                parsed = {}
            raw_actions = parsed.get("actions") or []
            if isinstance(raw_actions, list):
                actions_payload.extend(raw_actions)
            elif isinstance(raw_actions, dict):
                actions_payload.append(raw_actions)
            elif "type" in parsed:
                actions_payload.append(parsed)
        elif item_type == "message":
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text") or ""
                    if text:
                        text_parts.append(text)
        elif item_type == "reasoning":
            for content in item.get("summary") or []:
                if content.get("type") == "summary_text":
                    summary = content.get("text") or ""
                    if summary:
                        summary_parts.append(summary)

    actions = (
        normalize_actions(actions_payload, display_width=display_width, display_height=display_height)
        if actions_payload
        else []
    )
    stop = "actions" if actions else ("message" if text_parts else "error")
    return AgentResponse(
        response_id=data.get("id"),
        actions=actions,
        text="\n".join(text_parts) if text_parts else None,
        reasoning_summary="\n".join(summary_parts) if summary_parts else None,
        stop_reason=stop,
        raw_call_id=raw_call_id,
        extra={"raw_output_types": [item.get("type") for item in output]},
    )
