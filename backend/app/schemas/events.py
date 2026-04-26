from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "session_created",
    "agent_reasoning_summary",
    "agent_message",
    "tool_call",
    "action_executed",
    "screenshot",
    "task_status",
    "warning",
    "error",
]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EventType
    session_id: str
    ts: float
    sequence: int = Field(ge=1)


class SessionCreatedEvent(EventEnvelope):
    type: Literal["session_created"] = "session_created"


class AgentReasoningSummaryEvent(EventEnvelope):
    type: Literal["agent_reasoning_summary"] = "agent_reasoning_summary"
    text: str


class AgentMessageEvent(EventEnvelope):
    type: Literal["agent_message"] = "agent_message"
    text: str


class ToolCallEvent(EventEnvelope):
    type: Literal["tool_call"] = "tool_call"
    tool: str
    args: dict[str, Any]


class ActionExecutedEvent(EventEnvelope):
    type: Literal["action_executed"] = "action_executed"
    action: dict[str, Any]
    duration_ms: int = Field(ge=0)
    status: Literal["ok", "error"]
    error_code: str | None = None
    message: str | None = None


class ScreenshotEvent(EventEnvelope):
    type: Literal["screenshot"] = "screenshot"
    url: str
    thumb_url: str
    sha256: str


class TaskStatusEvent(EventEnvelope):
    type: Literal["task_status"] = "task_status"
    label: str
    state: Literal["queued", "running", "done", "error", "interrupted"]
    step: int | None = Field(default=None, ge=0)
    max_steps: int | None = Field(default=None, ge=1)


class WarningEvent(EventEnvelope):
    type: Literal["warning"] = "warning"
    code: str
    message: str


class ErrorEvent(EventEnvelope):
    type: Literal["error"] = "error"
    code: str
    message: str


AgentEvent = Annotated[
    SessionCreatedEvent
    | AgentReasoningSummaryEvent
    | AgentMessageEvent
    | ToolCallEvent
    | ActionExecutedEvent
    | ScreenshotEvent
    | TaskStatusEvent
    | WarningEvent
    | ErrorEvent,
    Field(discriminator="type"),
]
