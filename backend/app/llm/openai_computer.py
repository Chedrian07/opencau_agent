from __future__ import annotations

import asyncio
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
from app.llm.prompts import screen_feedback_text, system_instructions
from app.llm.tool_schema import computer_tool_schema


SYSTEM_INSTRUCTIONS = "You operate a remote Ubuntu desktop sandbox via the computer tool."


class OpenAIComputerAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=settings.llm_request_timeout_sec,
            headers={
                "authorization": f"Bearer {settings.llm_api_key}",
                "content-type": "application/json",
            },
        )
        self.capability = AdapterCapability(
            profile=settings.llm_profile,
            tool_mode=settings.llm_tool_mode,
            state_mode=settings.llm_state_mode,
            supports_vision=settings.llm_supports_vision,
            supports_tool_calls=settings.llm_supports_tool_calls,
            supports_native_computer=True,
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
        if screenshot is not None:
            content.append({"type": "input_image", "image_url": screenshot.data_url})
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "instructions": system_instructions(self._settings, native_computer=True),
            "tools": [
                computer_tool_schema(
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
            raise RuntimeError("previous response has no computer_call id")
        success = all(result.status == "ok" for result in action_results)
        feedback_text = screen_feedback_text(
            previous=previous,
            action_results=action_results,
            screenshot=screenshot,
        )
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "instructions": system_instructions(self._settings, native_computer=True),
            "previous_response_id": previous.response_id,
            "tools": [
                computer_tool_schema(
                    display_width=self._settings.display_width,
                    display_height=self._settings.display_height,
                )
            ],
            "tool_choice": "auto",
            "input": [
                {
                    "type": "computer_call_output",
                    "call_id": previous.raw_call_id,
                    "output": {
                        "type": "computer_screenshot",
                        "image_url": screenshot.data_url,
                    },
                    "acknowledged_safety_checks": [],
                }
            ],
        }
        if not success:
            body["input"].append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Some actions failed. Inspect the screenshot, recover, or report the failure.",
                        }
                    ],
                }
            )
        if previous.extra.get("last_screen_changed") is False:
            body["input"].append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": feedback_text}],
                }
            )
        return await self._send(body)

    async def _send(self, body: dict[str, Any]) -> AgentResponse:
        response = await self._post_responses_with_retry(body)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI Responses error {response.status_code}: {response.text[:1000]}"
            )
        data = response.json()
        return _parse_response(
            data,
            display_width=self._settings.display_width,
            display_height=self._settings.display_height,
        )

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
        raise RuntimeError("OpenAI Responses request timed out after retry") from last_exc


def _parse_response(
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
        if item_type == "computer_call":
            raw_call_id = item.get("call_id") or item.get("id")
            actions = item.get("action") or item.get("actions") or []
            if isinstance(actions, dict):
                actions_payload.append(actions)
            elif isinstance(actions, list):
                actions_payload.extend(actions)
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
