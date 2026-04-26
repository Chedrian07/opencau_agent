from typing import Literal

from pydantic import BaseModel, Field

SESSION_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,79}$"


class CreateSessionRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN, min_length=3, max_length=80)


class SessionResponse(BaseModel):
    session_id: str
    status: Literal["created", "running", "stopped", "missing"]
    container_id: str | None = None
    container_name: str | None = None


class CommandRequest(BaseModel):
    operation: Literal["healthcheck", "screenshot", "xdotool_click_type"]


class CommandResult(BaseModel):
    operation: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
