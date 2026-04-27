from __future__ import annotations

from typing import Any

ACTION_ENUM = [
    "screenshot",
    "click",
    "double_click",
    "right_click",
    "move",
    "drag",
    "type",
    "keypress",
    "scroll",
    "wait",
    "cursor_position",
]


def function_tool_schema(*, display_width: int, display_height: int) -> dict[str, Any]:
    return {
        "type": "function",
        "name": "computer",
            "description": (
                "Control the Ubuntu desktop using mouse, keyboard, scrolling, waiting, and screenshots."
                f" Display is {display_width}x{display_height}. Coordinates use 0,0 at the top-left."
                " Click the center of visible targets, not their label or top-left edge."
                " Always batch related actions in a single call. Take a screenshot before deciding the next step."
            ),
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string", "enum": ACTION_ENUM},
                            "x": {"type": "integer", "minimum": 0, "maximum": display_width - 1},
                            "y": {"type": "integer", "minimum": 0, "maximum": display_height - 1},
                            "button": {
                                "type": "string",
                                "enum": ["left", "right", "middle", "wheel", "back", "forward"],
                            },
                            "text": {"type": "string", "maxLength": 8000},
                            "keys": {
                                "type": "array",
                                "items": {"type": "string", "maxLength": 64},
                                "maxItems": 16,
                            },
                            "path": {
                                "type": "array",
                                "minItems": 2,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "x": {"type": "integer", "minimum": 0, "maximum": display_width - 1},
                                        "y": {"type": "integer", "minimum": 0, "maximum": display_height - 1},
                                    },
                                    "required": ["x", "y"],
                                },
                            },
                            "scroll_x": {"type": "integer"},
                            "scroll_y": {"type": "integer"},
                            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 30000},
                        },
                        "required": ["type"],
                    },
                }
            },
            "required": ["actions"],
            "additionalProperties": False,
        },
    }


def computer_tool_schema(*, display_width: int, display_height: int) -> dict[str, Any]:
    return {
        "type": "computer",
        "display_width": display_width,
        "display_height": display_height,
        "environment": "linux",
    }
