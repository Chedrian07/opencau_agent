import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.llm.base import ActionResult, AgentResponse, Screenshot
from app.llm.prompts import action_feedback_payload, screen_feedback_text, system_instructions
from app.schemas.actions import Action


class LlmPromptTests(unittest.TestCase):
    def test_system_instructions_include_panel_browser_hint(self) -> None:
        settings = Settings(_env_file=None, llm_profile="mock")

        text = system_instructions(settings, native_computer=False)

        self.assertIn("bottom-panel browser launcher", text)
        self.assertIn("(985,1053)", text)
        self.assertIn("do not open terminals", text)

    def test_return_feedback_asks_model_to_finish_when_page_visible(self) -> None:
        previous = AgentResponse(
            response_id="r1",
            actions=[],
            text=None,
            reasoning_summary=None,
            stop_reason="actions",
            extra={"last_screen_changed": True, "unchanged_screen_count": 0},
        )
        result = ActionResult(
            action=Action(type="keypress", keys=["Return"]),
            status="ok",
            duration_ms=7,
        )
        screenshot = Screenshot(data_url="data:image/png;base64,AA==", width=1920, height=1080, sha256="b" * 64)

        text = screen_feedback_text(previous=previous, action_results=[result], screenshot=screenshot)
        payload = action_feedback_payload(previous=previous, action_results=[result], screenshot=screenshot)

        self.assertIn("finish with a concise final message", text)
        self.assertIn("navigation_hint", payload)

    def test_screen_feedback_includes_recovery_hint_for_missed_firefox_click(self) -> None:
        previous = AgentResponse(
            response_id="r1",
            actions=[],
            text=None,
            reasoning_summary=None,
            stop_reason="actions",
            extra={"last_screen_changed": False, "unchanged_screen_count": 1},
        )
        result = ActionResult(
            action=Action(type="click", x=37, y=282),
            status="ok",
            duration_ms=10,
        )
        screenshot = Screenshot(data_url="data:image/png;base64,AA==", width=1920, height=1080, sha256="a" * 64)

        text = screen_feedback_text(previous=previous, action_results=[result], screenshot=screenshot)
        payload = action_feedback_payload(previous=previous, action_results=[result], screenshot=screenshot)

        self.assertIn("did not visually change", text)
        self.assertIn("(985,1053)", text)
        self.assertEqual(payload["screen_changed"], False)
        self.assertIn("recovery_hint", payload)


if __name__ == "__main__":
    unittest.main()
