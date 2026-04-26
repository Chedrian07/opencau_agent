import json
import sys
import unittest
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.sandbox.action_executor import ActionExecutor
from app.schemas.actions import Action


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_profile="mock",
        sandbox_controller_url="http://sandbox-controller:8100",
        display_width=1920,
        display_height=1080,
        action_timeout_sec=10,
    )


class ActionExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_post_returns_ok_result(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["json"] = json.loads(request.content.decode())
            return httpx.Response(
                200,
                json={"status": "ok", "duration_ms": 120, "output": "ok"},
            )

        transport = httpx.MockTransport(handler)
        settings = _settings()
        executor = ActionExecutor(settings)
        action = Action(type="click", x=100, y=200)

        async with httpx.AsyncClient(transport=transport) as client:
            result = await executor.execute(
                session_id="sess1",
                action=action,
                client=client,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.duration_ms, 120)
        self.assertEqual(result.output, "ok")
        self.assertIsNone(result.error_code)
        self.assertEqual(captured["method"], "POST")
        self.assertIn("/sessions/sess1/actions", captured["url"])
        self.assertEqual(captured["json"]["type"], "click")
        self.assertEqual(captured["json"]["x"], 100)
        self.assertEqual(captured["json"]["y"], 200)

    async def test_500_response_returns_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        transport = httpx.MockTransport(handler)
        settings = _settings()
        executor = ActionExecutor(settings)
        action = Action(type="click", x=10, y=10)

        async with httpx.AsyncClient(transport=transport) as client:
            result = await executor.execute(
                session_id="sess2",
                action=action,
                client=client,
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "SANDBOX_HTTP_ERROR")
        self.assertIn("500", (result.message or ""))

    async def test_out_of_bounds_action_short_circuits(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"status": "ok", "duration_ms": 0})

        transport = httpx.MockTransport(handler)
        settings = _settings()
        executor = ActionExecutor(settings)
        # display is 1920x1080; x=5000 is out of bounds.
        action = Action(type="click", x=5000, y=10)

        async with httpx.AsyncClient(transport=transport) as client:
            result = await executor.execute(
                session_id="sess3",
                action=action,
                client=client,
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "ACTION_OUT_OF_BOUNDS")
        self.assertEqual(result.duration_ms, 0)
        # The transport must NOT have been called.
        self.assertEqual(calls, [])

    async def test_status_field_other_than_ok_marks_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "error",
                    "duration_ms": 5,
                    "error_code": "XDOTOOL_FAIL",
                    "message": "no display",
                },
            )

        transport = httpx.MockTransport(handler)
        settings = _settings()
        executor = ActionExecutor(settings)
        action = Action(type="click", x=10, y=10)

        async with httpx.AsyncClient(transport=transport) as client:
            result = await executor.execute(
                session_id="sess4",
                action=action,
                client=client,
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error_code, "XDOTOOL_FAIL")
        self.assertEqual(result.message, "no display")
        self.assertEqual(result.duration_ms, 5)


if __name__ == "__main__":
    unittest.main()
