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

ACTION_DESCRIPTIONS = {
    "screenshot": "Capture the current screen when you need to observe before deciding.",
    "click": "Single left click at the visual center of a target; use this for buttons, browser controls, and panel launchers.",
    "double_click": "Double-click at the visual center of a desktop file/icon only; do not double-click panel launchers.",
    "right_click": "Open a context menu at a visible target.",
    "move": "Move the pointer without clicking.",
    "drag": "Drag along a path of at least two points.",
    "type": "Type literal text into the focused field.",
    "keypress": "Press one key or a chord such as Ctrl+L or Return.",
    "scroll": "Scroll at a visible point using scroll_x/scroll_y.",
    "wait": "Wait for UI changes, page loads, or app launch.",
    "cursor_position": "Ask for the current cursor position.",
}


def function_tool_schema(*, display_width: int, display_height: int) -> dict[str, Any]:
    return {
        "type": "function",
        "name": "computer",
        "description": (
            "Control a remote Ubuntu desktop using only GUI actions. "
            f"The display is {display_width}x{display_height}; coordinates use (0,0) at the top-left. "
            "Click the center of visible targets, not labels, borders, or top-left icon corners. "
            "The home desktop is intentionally noexec, so do not use desktop .desktop launchers. "
            "To open Firefox, single-click the trusted bottom-panel browser launcher: the blue globe icon "
            "near the lower center, about (985,1053) at 1920x1080. Do not click the blank desktop above "
            "the panel around y=970. If the screen does not change, do not "
            "repeat the same coordinate; wait briefly, inspect the screenshot, then choose a visible target."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "description": (
                        "Ordered GUI actions. Keep batches small and purposeful: for example "
                        "click + wait + screenshot when launching an app from the panel."
                    ),
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ACTION_ENUM,
                                "description": "; ".join(
                                    f"{name}: {ACTION_DESCRIPTIONS[name]}" for name in ACTION_ENUM
                                ),
                            },
                            "x": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": display_width - 1,
                                "description": "Horizontal screen coordinate. Use the target center.",
                            },
                            "y": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": display_height - 1,
                                "description": "Vertical screen coordinate. Use the target center.",
                            },
                            "button": {
                                "type": "string",
                                "enum": ["left", "right", "middle", "wheel", "back", "forward"],
                                "description": "Mouse button; omit for normal left-click.",
                            },
                            "text": {
                                "type": "string",
                                "maxLength": 8000,
                                "description": "Literal text to type into the focused UI element.",
                            },
                            "keys": {
                                "type": "array",
                                "description": "Keyboard chord, e.g. ['Ctrl','L'] or ['Return'].",
                                "items": {"type": "string", "maxLength": 64},
                                "maxItems": 16,
                            },
                            "path": {
                                "type": "array",
                                "description": "Drag path points in order.",
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
                            "scroll_x": {"type": "integer", "description": "Horizontal scroll delta."},
                            "scroll_y": {"type": "integer", "description": "Vertical scroll delta."},
                            "duration_ms": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 30000,
                                "description": "Wait duration in milliseconds.",
                            },
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
