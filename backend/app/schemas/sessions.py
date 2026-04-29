from typing import Literal

from pydantic import BaseModel, Field

SESSION_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,79}$"


class CreateSessionRequest(BaseModel):
    session_id: str | None = Field(default=None, pattern=SESSION_ID_PATTERN, min_length=3, max_length=80)


class SessionInfo(BaseModel):
    session_id: str
    status: Literal["created", "running", "stopped", "missing"]
    vnc_url: str | None = None
    container_id: str | None = None


class CommandSmokeRequest(BaseModel):
    operation: Literal["healthcheck", "screenshot", "xdotool_click_type", "active_window_title"]


class CommandSmokeResult(BaseModel):
    operation: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
