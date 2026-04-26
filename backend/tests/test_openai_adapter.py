import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.openai_computer import _parse_response


class ParseResponseTests(unittest.TestCase):
    def test_computer_call_with_dict_action_produces_one_action(self) -> None:
        data = {
            "id": "resp_abc",
            "output": [
                {
                    "type": "computer_call",
                    "call_id": "call_42",
                    "action": {"type": "click", "x": 100, "y": 200},
                }
            ],
        }

        response = _parse_response(data)

        self.assertEqual(response.response_id, "resp_abc")
        self.assertEqual(len(response.actions), 1)
        self.assertEqual(response.actions[0].type, "click")
        self.assertEqual(response.actions[0].x, 100)
        self.assertEqual(response.actions[0].y, 200)
        self.assertEqual(response.stop_reason, "actions")
        self.assertEqual(response.raw_call_id, "call_42")
        self.assertIsNone(response.text)

    def test_computer_call_falls_back_to_id_when_call_id_missing(self) -> None:
        data = {
            "id": "resp_x",
            "output": [
                {
                    "type": "computer_call",
                    "id": "ccall_1",
                    "action": {"type": "screenshot"},
                }
            ],
        }

        response = _parse_response(data)

        self.assertEqual(response.raw_call_id, "ccall_1")
        self.assertEqual(len(response.actions), 1)
        self.assertEqual(response.actions[0].type, "screenshot")

    def test_message_only_response_has_message_stop_reason(self) -> None:
        data = {
            "id": "resp_msg",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Task done."},
                    ],
                }
            ],
        }

        response = _parse_response(data)

        self.assertEqual(response.stop_reason, "message")
        self.assertEqual(response.text, "Task done.")
        self.assertEqual(response.actions, [])
        self.assertIsNone(response.raw_call_id)

    def test_message_text_content_type_also_supported(self) -> None:
        data = {
            "id": "resp_msg2",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "text", "text": "Hello"},
                    ],
                }
            ],
        }

        response = _parse_response(data)

        self.assertEqual(response.stop_reason, "message")
        self.assertEqual(response.text, "Hello")

    def test_reasoning_summary_populated(self) -> None:
        data = {
            "id": "resp_r",
            "output": [
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "Thinking briefly."},
                    ],
                },
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Done."}],
                },
            ],
        }

        response = _parse_response(data)

        self.assertEqual(response.reasoning_summary, "Thinking briefly.")
        self.assertEqual(response.text, "Done.")
        self.assertEqual(response.stop_reason, "message")

    def test_empty_output_yields_error_stop_reason(self) -> None:
        data = {"id": "resp_empty", "output": []}

        response = _parse_response(data)

        self.assertEqual(response.stop_reason, "error")
        self.assertEqual(response.actions, [])
        self.assertIsNone(response.text)

    def test_extra_carries_raw_output_types(self) -> None:
        data = {
            "id": "r1",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "computer_call",
                    "call_id": "c1",
                    "action": {"type": "wait", "duration_ms": 100},
                },
            ],
        }

        response = _parse_response(data)

        self.assertEqual(response.extra["raw_output_types"], ["reasoning", "computer_call"])


if __name__ == "__main__":
    unittest.main()
