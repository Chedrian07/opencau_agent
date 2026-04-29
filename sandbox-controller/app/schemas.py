from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SESSION_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,79}$"

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


class CreateSessionRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN, min_length=3, max_length=80)


class SessionResponse(BaseModel):
    session_id: str
    status: Literal["created", "running", "stopped", "missing"]
    container_id: str | None = None
    container_name: str | None = None


class CommandRequest(BaseModel):
    operation: Literal["healthcheck", "screenshot", "xdotool_click_type", "active_window_title"]


class CommandResult(BaseModel):
    operation: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ActionType
    x: int | None = None
    y: int | None = None
    button: str | None = None
    text: str | None = Field(default=None, max_length=8000)
    keys: list[str] | None = None
    path: list[dict[str, int]] | None = None
    scroll_x: int | None = None
    scroll_y: int | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=30000)


class ActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    duration_ms: int = Field(ge=0)
    output: str = ""
    error_code: str | None = None
    message: str | None = None
    extra: dict[str, Any] | None = None
