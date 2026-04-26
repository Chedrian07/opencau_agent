import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.function_computer import parse_function_response


class ParseFunctionResponseTests(unittest.TestCase):
    def test_function_call_with_string_arguments(self) -> None:
        data = {
            "id": "resp_fc",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_77",
                    "name": "computer",
                    "arguments": json.dumps(
                        {
                            "actions": [
                                {"type": "click", "x": 50, "y": 60},
                                {"type": "wait", "duration_ms": 500},
                            ]
                        }
                    ),
                }
            ],
        }

        response = parse_function_response(data)

        self.assertEqual(response.response_id, "resp_fc")
        self.assertEqual(len(response.actions), 2)
        self.assertEqual(response.actions[0].type, "click")
        self.assertEqual(response.actions[0].x, 50)
        self.assertEqual(response.actions[1].type, "wait")
        self.assertEqual(response.actions[1].duration_ms, 500)
        self.assertEqual(response.stop_reason, "actions")
        self.assertEqual(response.raw_call_id, "call_77")

    def test_tool_call_alias_supported(self) -> None:
        data = {
            "id": "resp_tc",
            "output": [
                {
                    "type": "tool_call",
                    "id": "tcall_1",
                    "arguments": {"actions": [{"type": "screenshot"}]},
                }
            ],
        }

        response = parse_function_response(data)

        self.assertEqual(response.raw_call_id, "tcall_1")
        self.assertEqual(len(response.actions), 1)
        self.assertEqual(response.actions[0].type, "screenshot")

    def test_invalid_json_arguments_yields_no_actions(self) -> None:
        data = {
            "id": "resp_bad",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "arguments": "{not json",
                }
            ],
        }

        response = parse_function_response(data)

        self.assertEqual(response.actions, [])
        # No actions and no text -> error stop reason.
        self.assertEqual(response.stop_reason, "error")
        self.assertEqual(response.raw_call_id, "c1")

    def test_message_only_response(self) -> None:
        data = {
            "id": "resp_m",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "All done."},
                    ],
                }
            ],
        }

        response = parse_function_response(data)

        self.assertEqual(response.stop_reason, "message")
        self.assertEqual(response.text, "All done.")
        self.assertEqual(response.actions, [])
        self.assertIsNone(response.raw_call_id)

    def test_reasoning_summary_populated(self) -> None:
        data = {
            "id": "resp_r",
            "output": [
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "Step plan."},
                    ],
                },
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "arguments": json.dumps({"actions": [{"type": "screenshot"}]}),
                },
            ],
        }

        response = parse_function_response(data)

        self.assertEqual(response.reasoning_summary, "Step plan.")
        self.assertEqual(len(response.actions), 1)
        self.assertEqual(response.stop_reason, "actions")


if __name__ == "__main__":
    unittest.main()
