import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.llm.preflight import (
    PreflightCheck,
    PreflightReport,
    report_to_dict,
    run_preflight,
)


def _settings(**overrides) -> Settings:
    """Build a Settings instance bypassing the on-disk .env file."""
    return Settings(_env_file=None, **overrides)


class RunPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_profile_with_empty_key_skips_reachability(self) -> None:
        settings = _settings(llm_profile="mock", llm_api_key="")

        report = await run_preflight(settings)

        check_names = [check.name for check in report.checks]
        # Mock profile + empty key => no api_key error.
        self.assertNotIn("api_key", check_names)
        # Reachability is skipped for the mock profile.
        reach = next(c for c in report.checks if c.name == "responses_reachable")
        self.assertEqual(reach.status, "skipped")

    async def test_openai_native_with_empty_key_reports_api_key_error(self) -> None:
        settings = _settings(
            llm_profile="openai-native",
            llm_api_key="",
            llm_tool_mode="openai_computer",
            llm_state_mode="server",
        )

        report = await run_preflight(settings)

        api_key_check = next(
            (c for c in report.checks if c.name == "api_key"), None
        )
        self.assertIsNotNone(api_key_check)
        self.assertEqual(api_key_check.status, "error")
        self.assertEqual(report.overall, "error")
        # Reachability should still be skipped because the API key is missing.
        reach = next(c for c in report.checks if c.name == "responses_reachable")
        self.assertEqual(reach.status, "skipped")

    async def test_lmstudio_responses_with_openai_computer_tool_mode_errors(self) -> None:
        settings = _settings(
            llm_profile="lmstudio-responses",
            llm_api_key="",
            llm_tool_mode="openai_computer",
            llm_state_mode="server",
        )

        report = await run_preflight(settings)

        tool_mode = next(
            (c for c in report.checks if c.name == "tool_mode"), None
        )
        self.assertIsNotNone(tool_mode)
        self.assertEqual(tool_mode.status, "error")
        self.assertEqual(report.overall, "error")

    async def test_overall_warning_when_no_errors_only_warnings(self) -> None:
        # ollama-stateless expects manual state mode + function_computer.
        # Using server state_mode triggers a warning. Empty api_key would
        # normally raise an api_key error -- but ollama-stateless does not
        # require a real key. We avoid that by leaving the api_key empty AND
        # checking via the existing rule: api_key error fires only when
        # profile != mock AND key is empty. So use a placeholder key and
        # monkey-patch httpx.AsyncClient to skip the real probe quickly.
        from unittest.mock import AsyncMock, MagicMock, patch

        settings = _settings(
            llm_profile="ollama-stateless",
            llm_api_key="placeholder",
            llm_tool_mode="function_computer",
            llm_state_mode="server",  # triggers warning
            llm_supports_tool_calls=True,
            llm_supports_vision=True,
        )

        fake_response = MagicMock()
        fake_response.status_code = 200

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        fake_client.get = AsyncMock(return_value=fake_response)

        with patch("app.llm.preflight.httpx.AsyncClient", return_value=fake_client):
            report = await run_preflight(settings)

        # state_mode warning expected, no error checks should be present.
        statuses = [c.status for c in report.checks]
        self.assertNotIn("error", statuses)
        self.assertIn("warning", statuses)
        self.assertEqual(report.overall, "warning")


class ReportToDictTests(unittest.TestCase):
    def test_returns_nested_structure(self) -> None:
        report = PreflightReport(
            profile="mock",
            model="m1",
            base_url="http://x/v1",
            tool_mode="openai_computer",
            state_mode="server",
            overall="ok",
            checks=[
                PreflightCheck(name="api_key", status="ok", detail="present"),
                PreflightCheck(name="responses_reachable", status="skipped", detail="mock"),
            ],
        )

        result = report_to_dict(report)

        self.assertEqual(result["profile"], "mock")
        self.assertEqual(result["model"], "m1")
        self.assertEqual(result["base_url"], "http://x/v1")
        self.assertEqual(result["tool_mode"], "openai_computer")
        self.assertEqual(result["state_mode"], "server")
        self.assertEqual(result["overall"], "ok")
        self.assertEqual(len(result["checks"]), 2)
        self.assertEqual(
            result["checks"][0],
            {"name": "api_key", "status": "ok", "detail": "present"},
        )
        self.assertEqual(
            result["checks"][1],
            {"name": "responses_reachable", "status": "skipped", "detail": "mock"},
        )


if __name__ == "__main__":
    unittest.main()
