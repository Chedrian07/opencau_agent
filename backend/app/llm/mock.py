from __future__ import annotations

import time
import uuid

from app.config import Settings
from app.llm.base import (
    ActionResult,
    AdapterCapability,
    AgentResponse,
    Screenshot,
)
from app.schemas.actions import Action


class MockComputerAdapter:
    """Deterministic adapter used when no LLM credentials are configured.

    The adapter performs a screenshot then issues a final agent_message so the
    full event pipeline is exercised without an external API key.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.capability = AdapterCapability(
            profile="mock",
            tool_mode=settings.llm_tool_mode,
            state_mode=settings.llm_state_mode,
            supports_vision=False,
            supports_tool_calls=True,
            supports_native_computer=False,
            model="mock-computer",
            base_url=settings.llm_base_url,
        )

    async def aclose(self) -> None:
        return None

    async def create_initial_response(
        self,
        *,
        session_id: str,
        user_message: str,
        screenshot: Screenshot | None,
    ) -> AgentResponse:
        action = Action(type="screenshot")
        return AgentResponse(
            response_id=f"mock-{uuid.uuid4().hex[:8]}",
            actions=[action],
            text=None,
            reasoning_summary="Mock adapter is online. Capturing a screenshot before continuing.",
            stop_reason="actions",
            raw_call_id=f"call-{uuid.uuid4().hex[:8]}",
            extra={"mock": True, "ts": time.time(), "user_message": user_message},
        )

    async def continue_after_actions(
        self,
        *,
        previous: AgentResponse,
        action_results: list[ActionResult],
        screenshot: Screenshot,
    ) -> AgentResponse:
        text = (
            "Mock adapter completed the requested action."
            " Configure LLM_PROFILE=openai-native and LLM_API_KEY for real automation."
        )
        return AgentResponse(
            response_id=f"mock-{uuid.uuid4().hex[:8]}",
            actions=[],
            text=text,
            reasoning_summary="Final summary from mock adapter.",
            stop_reason="message",
            raw_call_id=None,
            extra={"mock": True, "ts": time.time()},
        )
