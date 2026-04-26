from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.schemas.actions import Action

ResponseStop = Literal["actions", "message", "error"]


@dataclass(frozen=True)
class Screenshot:
    data_url: str
    width: int
    height: int
    sha256: str

    @classmethod
    def from_png_bytes(cls, image: bytes, *, width: int, height: int, sha256: str) -> "Screenshot":
        import base64

        encoded = base64.b64encode(image).decode("ascii")
        return cls(
            data_url=f"data:image/png;base64,{encoded}",
            width=width,
            height=height,
            sha256=sha256,
        )


@dataclass(frozen=True)
class ActionResult:
    action: Action
    status: Literal["ok", "error"]
    duration_ms: int
    output: str = ""
    error_code: str | None = None
    message: str | None = None


@dataclass
class AgentResponse:
    response_id: str | None
    actions: list[Action]
    text: str | None
    reasoning_summary: str | None
    stop_reason: ResponseStop
    raw_call_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterCapability:
    profile: str
    tool_mode: str
    state_mode: str
    supports_vision: bool
    supports_tool_calls: bool
    supports_native_computer: bool
    model: str
    base_url: str


class LLMAdapter(Protocol):
    capability: AdapterCapability

    async def create_initial_response(
        self,
        *,
        session_id: str,
        user_message: str,
        screenshot: Screenshot | None,
    ) -> AgentResponse: ...

    async def continue_after_actions(
        self,
        *,
        previous: AgentResponse,
        action_results: list[ActionResult],
        screenshot: Screenshot,
    ) -> AgentResponse: ...

    async def aclose(self) -> None: ...
