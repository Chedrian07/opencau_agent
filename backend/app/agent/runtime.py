from __future__ import annotations

import asyncio

from app.agent.events import event_broker
from app.agent.loop import AgentLoopDeps, run_agent_loop
from app.config import Settings, get_settings
from app.llm.factory import build_adapter
from app.sandbox.action_executor import ActionExecutor
from app.sandbox.client import SandboxClient
from app.storage.session_store import RedisSessionManager
from app.storage.sqlite import SQLiteStore
from app.storage.screenshot_store import ScreenshotStore


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
        sqlite_store: SQLiteStore | None = None,
        session_manager: RedisSessionManager | None = None,
        settings: Settings | None = None,
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
                    sqlite_store=sqlite_store,
                    session_manager=session_manager,
                    settings=settings or get_settings(),
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
            task.cancel()
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
        self._interrupts.discard(session_id)

    async def _run_message(
        self,
        *,
        session_id: str,
        text: str,
        sandbox_client: SandboxClient,
        screenshot_store: ScreenshotStore,
        sqlite_store: SQLiteStore | None,
        session_manager: RedisSessionManager | None,
        settings: Settings,
    ) -> None:
        if session_manager is not None:
            await session_manager.touch(session_id)
        deps = AgentLoopDeps(
            settings=settings,
            sandbox_client=sandbox_client,
            screenshot_store=screenshot_store,
            action_executor=ActionExecutor(settings),
            adapter_factory=lambda: build_adapter(settings),
            is_interrupted=lambda: self._is_interrupted(session_id),
            sqlite_store=sqlite_store,
        )
        try:
            await run_agent_loop(session_id=session_id, user_message=text, deps=deps)
        except Exception as exc:  # pragma: no cover - safety net
            await event_broker.publish(
                session_id,
                "error",
                code="AGENT_RUNTIME_ERROR",
                message=str(exc),
            )
            await event_broker.publish(
                session_id,
                "task_status",
                label="Runtime crashed",
                state="error",
            )
        finally:
            if session_manager is not None:
                await session_manager.touch(session_id)


agent_runtime = AgentRuntime()
