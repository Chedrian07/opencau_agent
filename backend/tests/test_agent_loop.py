import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.events import event_broker
from app.agent.loop import AgentLoopDeps, run_agent_loop
from app.config import Settings
from app.llm.base import ActionResult
from app.llm.mock import MockComputerAdapter
from app.sandbox.action_executor import ActionExecutor
from app.schemas.actions import Action
from app.storage.screenshot_store import ScreenshotStore


# Real 1x1 PNG bytes used by the fake sandbox client.
ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8cfc0f01f0006000301010005bf24310000000049454e44ae426082"
)


class _FakeSandboxClient:
    """Mimics the SandboxClient surface the agent loop calls."""

    def __init__(self, image: bytes) -> None:
        self._image = image
        self.capture_count = 0
        self.action_capture_count = 0

    async def capture_screenshot(self, session_id: str) -> bytes:  # noqa: ARG002
        self.capture_count += 1
        return self._image

    async def capture_action_screenshot(self, session_id: str) -> bytes | None:  # noqa: ARG002
        self.action_capture_count += 1
        return None


class _FakeActionExecutor(ActionExecutor):
    """ActionExecutor stub that returns synthetic ActionResults without HTTP."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.calls: list[Action] = []

    async def execute(
        self,
        *,
        session_id: str,
        action: Action,
        client: httpx.AsyncClient | None = None,
    ) -> ActionResult:  # noqa: ARG002
        self.calls.append(action)
        return ActionResult(
            action=action,
            status="ok",
            duration_ms=5,
            output="ok",
        )


def _settings(screenshot_dir: str) -> Settings:
    return Settings(
        _env_file=None,
        llm_profile="mock",
        sandbox_controller_url="http://sandbox-controller:8100",
        screenshot_dir=screenshot_dir,
        max_agent_steps=4,
        agent_timeout_sec=30,
        action_timeout_sec=5,
        repeated_action_threshold=5,
    )


class RunAgentLoopMockTests(unittest.IsolatedAsyncioTestCase):
    async def test_emits_expected_event_sequence_with_mock_adapter(self) -> None:
        session_id = "test-loop-session"

        # Reset broker state for this session before publishing anything.
        await event_broker.clear(session_id)

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(tmp)
            sandbox = _FakeSandboxClient(ONE_PIXEL_PNG)
            executor = _FakeActionExecutor(settings)
            store = ScreenshotStore(tmp)

            deps = AgentLoopDeps(
                settings=settings,
                sandbox_client=sandbox,  # type: ignore[arg-type]
                screenshot_store=store,
                action_executor=executor,
                adapter_factory=lambda: MockComputerAdapter(settings),
                is_interrupted=lambda: False,
            )

            await run_agent_loop(
                session_id=session_id,
                user_message="Please open a browser",
                deps=deps,
            )

            history = await event_broker.history(session_id)

        types_in_order = [event["type"] for event in history]

        # The loop must emit at least one event of each of these kinds.
        for expected in (
            "task_status",
            "agent_reasoning_summary",
            "screenshot",
            "tool_call",
            "action_executed",
            "agent_message",
        ):
            self.assertIn(
                expected,
                types_in_order,
                msg=f"Missing event type {expected!r} in {types_in_order!r}",
            )

        # Two screenshot events expected: initial + post-action.
        screenshot_count = sum(1 for t in types_in_order if t == "screenshot")
        self.assertGreaterEqual(screenshot_count, 2)

        # task_status events bracket the run: first 'running', last 'done'.
        task_status_events = [
            event for event in history if event["type"] == "task_status"
        ]
        self.assertGreaterEqual(len(task_status_events), 2)
        self.assertEqual(task_status_events[0]["state"], "running")
        self.assertEqual(task_status_events[-1]["state"], "done")

        # tool_call must come before agent_message (cause/effect ordering).
        tool_call_idx = types_in_order.index("tool_call")
        action_executed_idx = types_in_order.index("action_executed")
        agent_message_idx = types_in_order.index("agent_message")
        self.assertLess(tool_call_idx, action_executed_idx)
        self.assertLess(action_executed_idx, agent_message_idx)

        # Sanity: the fake sandbox screenshot was captured at least twice
        # (initial + post-action) and the executor ran the mock screenshot action.
        self.assertGreaterEqual(sandbox.capture_count, 2)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(executor.calls[0].type, "screenshot")

        # All screenshot events should reference URLs under /api/sessions/...
        screenshot_events = [event for event in history if event["type"] == "screenshot"]
        self.assertGreaterEqual(len(screenshot_events), 2)
        for event in screenshot_events:
            self.assertIn(f"/api/sessions/{session_id}/screenshots/", event["url"])
            self.assertEqual(len(event["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
