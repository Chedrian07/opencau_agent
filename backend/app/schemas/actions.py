from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ActionType = Literal[
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

MouseButton = Literal["left", "right", "middle", "wheel", "back", "forward"]

POINT_ACTIONS: frozenset[str] = frozenset(
    {"click", "double_click", "right_click", "move", "scroll"}
)


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ActionType

    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    button: MouseButton | None = None

    text: str | None = Field(default=None, max_length=8000)
    keys: list[str] | None = None

    path: list[Point] | None = None

    scroll_x: int | None = None
    scroll_y: int | None = None

    duration_ms: int | None = Field(default=None, ge=0, le=30000)

    @model_validator(mode="after")
    def _validate_payload(self) -> Action:
        if self.type in POINT_ACTIONS:
            if self.x is None or self.y is None:
                raise ValueError(f"action '{self.type}' requires x and y")
        if self.type == "drag":
            if not self.path or len(self.path) < 2:
                raise ValueError("drag action requires path with at least 2 points")
        if self.type == "type":
            if not self.text:
                raise ValueError("type action requires text")
        if self.type == "keypress":
            if not self.keys:
                raise ValueError("keypress action requires keys")
        if self.type == "wait":
            if self.duration_ms is None:
                raise ValueError("wait action requires duration_ms")
        if self.type == "scroll":
            if self.scroll_x is None and self.scroll_y is None:
                raise ValueError("scroll action requires scroll_x or scroll_y")
        return self


class ActionValidationError(ValueError):
    """Raised when an action fails policy validation (e.g. out-of-bounds)."""


def ensure_within_display(action: Action, *, width: int, height: int) -> None:
    if action.x is not None and not 0 <= action.x < width:
        raise ActionValidationError(
            f"action x={action.x} is outside display width {width}"
        )
    if action.y is not None and not 0 <= action.y < height:
        raise ActionValidationError(
            f"action y={action.y} is outside display height {height}"
        )
    if action.path:
        for point in action.path:
            if not 0 <= point.x < width or not 0 <= point.y < height:
                raise ActionValidationError(
                    f"drag path point ({point.x},{point.y}) is outside display"
                )


def actions_match(left: Action, right: Action) -> bool:
    fields: tuple[str, ...] = ("type", "x", "y", "text", "button")
    return all(getattr(left, name) == getattr(right, name) for name in fields)


class ActionExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: dict[str, Any]
    status: Literal["ok", "error"]
    duration_ms: int = Field(ge=0)
    output: str = ""
    error_code: str | None = None
    message: str | None = None
