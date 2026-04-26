from __future__ import annotations

import asyncio
import time

from app.agent.events import event_broker
from app.sandbox.client import SandboxClient
from app.storage.screenshot_store import ScreenshotStore


def _operation_for_message(text: str) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("health", "status", "상태", "헬스")):
        return "healthcheck"
    if any(token in lowered for token in ("click", "type", "xdotool", "클릭", "입력", "타입", "테스트")):
        return "xdotool_click_type"
    return "screenshot"


class AgentRuntime:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._interrupts: set[str] = set()
        self._lock = asyncio.Lock()

    async def submit(
        self,
        *,
        session_id: str,
        text: str,
        sandbox_client: SandboxClient,
        screenshot_store: ScreenshotStore,
    ) -> bool:
        async with self._lock:
            current = self._tasks.get(session_id)
            if current is not None and not current.done():
                await event_broker.publish(
                    session_id,
                    "warning",
                    code="TASK_ALREADY_RUNNING",
                    message="A task is already running for this session.",
                )
                return False
            self._interrupts.discard(session_id)
            task = asyncio.create_task(
                self._run_message(
                    session_id=session_id,
                    text=text,
                    sandbox_client=sandbox_client,
                    screenshot_store=screenshot_store,
                )
            )
            self._tasks[session_id] = task
            task.add_done_callback(lambda completed: self._cleanup_task(session_id, completed))
            return True

    async def interrupt(self, session_id: str) -> None:
        async with self._lock:
            self._interrupts.add(session_id)
            task = self._tasks.get(session_id)
        if task is not None and not task.done():
            await event_broker.publish(
                session_id,
                "task_status",
                label="Interrupt requested",
                state="interrupted",
            )
        else:
            await event_broker.publish(
                session_id,
                "warning",
                code="NO_RUNNING_TASK",
                message="There is no running task to interrupt.",
            )

    def _is_interrupted(self, session_id: str) -> bool:
        return session_id in self._interrupts

    def _cleanup_task(self, session_id: str, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(session_id) is completed:
            self._tasks.pop(session_id, None)

    async def _run_message(
        self,
        *,
        session_id: str,
        text: str,
        sandbox_client: SandboxClient,
        screenshot_store: ScreenshotStore,
    ) -> None:
        operation = _operation_for_message(text)
        action = {"type": operation}
        await event_broker.publish(
            session_id,
            "task_status",
            label="Running desktop action",
            state="running",
            step=1,
            max_steps=2,
        )
        await event_broker.publish(
            session_id,
            "agent_reasoning_summary",
            text="Phase 2 smoke runner selected a safe sandbox operation while the LLM loop is being wired.",
        )
        await event_broker.publish(session_id, "tool_call", tool="computer", args={"actions": [action]})

        if self._is_interrupted(session_id):
            await self._finish_interrupted(session_id)
            return

        started = time.monotonic()
        try:
            result = await sandbox_client.run_smoke_command(session_id, operation)
            duration_ms = int((time.monotonic() - started) * 1000)
            status = "ok" if result.exit_code == 0 else "error"
            await event_broker.publish(
                session_id,
                "action_executed",
                action=action,
                duration_ms=duration_ms,
                status=status,
                error_code=None if status == "ok" else "SANDBOX_COMMAND_FAILED",
                message=result.stderr or result.stdout or None,
            )
            if status != "ok":
                await event_broker.publish(
                    session_id,
                    "error",
                    code="SANDBOX_COMMAND_FAILED",
                    message=result.stderr or "Sandbox command failed.",
                )
                return

            if self._is_interrupted(session_id):
                await self._finish_interrupted(session_id)
                return

            await event_broker.publish(
                session_id,
                "task_status",
                label="Capturing screenshot",
                state="running",
                step=2,
                max_steps=2,
            )
            image = await sandbox_client.capture_screenshot(session_id)
            screenshot = screenshot_store.save_png(session_id, image)
            await event_broker.publish(
                session_id,
                "screenshot",
                url=screenshot.url,
                thumb_url=screenshot.thumb_url,
                sha256=screenshot.sha256,
            )
            await event_broker.publish(
                session_id,
                "agent_message",
                text="Desktop action completed. The latest screenshot is available in the event stream.",
            )
            await event_broker.publish(
                session_id,
                "task_status",
                label="Desktop action complete",
                state="done",
                step=2,
                max_steps=2,
            )
        except Exception as exc:
            await event_broker.publish(
                session_id,
                "error",
                code="AGENT_RUNTIME_ERROR",
                message=str(exc),
            )
            await event_broker.publish(
                session_id,
                "task_status",
                label="Desktop action failed",
                state="error",
            )

    async def _finish_interrupted(self, session_id: str) -> None:
        await event_broker.publish(
            session_id,
            "task_status",
            label="Task interrupted",
            state="interrupted",
        )


agent_runtime = AgentRuntime()
