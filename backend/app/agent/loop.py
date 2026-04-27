from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.events import event_broker
from app.config import Settings
from app.llm.base import ActionResult, AgentResponse, LLMAdapter, Screenshot
from app.sandbox.action_executor import ActionExecutor
from app.sandbox.client import SandboxClient
from app.schemas.actions import Action, actions_match
from app.storage.sqlite import SQLiteStore
from app.storage.screenshot_store import ScreenshotMetadata, ScreenshotStore


@dataclass
class AgentLoopDeps:
    settings: Settings
    sandbox_client: SandboxClient
    screenshot_store: ScreenshotStore
    action_executor: ActionExecutor
    adapter_factory: Callable[[], LLMAdapter]
    is_interrupted: Callable[[], bool]
    sqlite_store: SQLiteStore | None = None


def _action_dump(action: Action) -> dict[str, Any]:
    return action.model_dump(exclude_none=True)


def _exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


async def _capture_screenshot(deps: AgentLoopDeps, session_id: str) -> tuple[Screenshot | None, ScreenshotMetadata | None]:
    try:
        action_image = await deps.sandbox_client.capture_action_screenshot(session_id)
    except Exception:
        action_image = None
    image = action_image or await deps.sandbox_client.capture_screenshot(session_id)
    metadata = deps.screenshot_store.save_png(session_id, image)
    if deps.sqlite_store is not None:
        deps.sqlite_store.record_screenshot(metadata)
    screenshot = Screenshot.from_png_bytes(
        image,
        width=deps.settings.display_width,
        height=deps.settings.display_height,
        sha256=metadata.sha256,
    )
    return screenshot, metadata


async def run_agent_loop(*, session_id: str, user_message: str, deps: AgentLoopDeps) -> None:
    settings = deps.settings
    adapter = deps.adapter_factory()

    await event_broker.publish(
        session_id,
        "agent_reasoning_summary",
        text=f"Profile {adapter.capability.profile} ({adapter.capability.model}) preparing to act.",
    )
    await event_broker.publish(
        session_id,
        "task_status",
        label="Capturing initial screenshot",
        state="running",
        step=0,
        max_steps=settings.max_agent_steps,
    )

    try:
        screenshot, metadata = await _capture_screenshot(deps, session_id)
    except asyncio.CancelledError:
        await adapter.aclose()
        raise
    except Exception as exc:
        await event_broker.publish(
            session_id,
            "error",
            code="SCREENSHOT_FAILURE",
            message=f"initial screenshot failed: {exc}",
        )
        await event_broker.publish(
            session_id,
            "task_status",
            label="Aborted",
            state="error",
        )
        await adapter.aclose()
        return

    if metadata is not None:
        await event_broker.publish(
            session_id,
            "screenshot",
            url=metadata.url,
            thumb_url=metadata.thumb_url,
            sha256=metadata.sha256,
        )

    try:
        response = await adapter.create_initial_response(
            session_id=session_id,
            user_message=user_message,
            screenshot=screenshot,
        )
    except asyncio.CancelledError:
        await adapter.aclose()
        raise
    except Exception as exc:
        await event_broker.publish(
            session_id,
            "error",
            code="LLM_RESPONSE_ERROR",
            message=_exception_message(exc),
        )
        await event_broker.publish(
            session_id,
            "task_status",
            label="LLM call failed",
            state="error",
        )
        await adapter.aclose()
        return

    started = time.monotonic()
    deadline = started + settings.agent_timeout_sec

    last_action_signature: tuple[Action, ...] | None = None
    repeat_count = 0

    try:
        for step in range(1, settings.max_agent_steps + 1):
            if deps.is_interrupted():
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="Interrupted by user",
                    state="interrupted",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return
            if time.monotonic() > deadline:
                await event_broker.publish(
                    session_id,
                    "warning",
                    code="AGENT_TIMEOUT",
                    message=f"Exceeded {settings.agent_timeout_sec}s budget",
                )
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="Timeout",
                    state="error",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return

            if response.reasoning_summary:
                await event_broker.publish(
                    session_id,
                    "agent_reasoning_summary",
                    text=response.reasoning_summary,
                )

            if response.stop_reason == "message" or not response.actions:
                if response.text:
                    await event_broker.publish(
                        session_id,
                        "agent_message",
                        text=response.text,
                    )
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="Task complete",
                    state="done",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return

            actions_payload = [_action_dump(action) for action in response.actions]
            await event_broker.publish(
                session_id,
                "tool_call",
                tool="computer",
                args={"actions": actions_payload},
            )
            await event_broker.publish(
                session_id,
                "task_status",
                label=f"Executing step {step}",
                state="running",
                step=step,
                max_steps=settings.max_agent_steps,
            )

            signature = tuple(response.actions)
            if last_action_signature is not None and len(signature) == len(last_action_signature) and all(
                actions_match(left, right) for left, right in zip(signature, last_action_signature)
            ):
                repeat_count += 1
            else:
                repeat_count = 0
                last_action_signature = signature
            if repeat_count >= settings.repeated_action_threshold:
                await event_broker.publish(
                    session_id,
                    "warning",
                    code="REPEATED_ACTION",
                    message=f"Same action repeated {repeat_count + 1} times; aborting loop",
                )
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="Repeated action loop",
                    state="error",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return

            results: list[ActionResult] = []
            async with _http_client(settings) as http:
                for action in response.actions:
                    if deps.is_interrupted():
                        await event_broker.publish(
                            session_id,
                            "task_status",
                            label="Interrupted mid-step",
                            state="interrupted",
                            step=step,
                            max_steps=settings.max_agent_steps,
                        )
                        return
                    result = await deps.action_executor.execute(
                        session_id=session_id, action=action, client=http
                    )
                    results.append(result)
                    await event_broker.publish(
                        session_id,
                        "action_executed",
                        action=_action_dump(action),
                        duration_ms=result.duration_ms,
                        status=result.status,
                        error_code=result.error_code,
                        message=result.message,
                    )

            try:
                screenshot, metadata = await _capture_screenshot(deps, session_id)
            except Exception as exc:
                await event_broker.publish(
                    session_id,
                    "error",
                    code="SCREENSHOT_FAILURE",
                    message=str(exc),
                )
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="Screenshot failed",
                    state="error",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return
            if metadata is not None:
                await event_broker.publish(
                    session_id,
                    "screenshot",
                    url=metadata.url,
                    thumb_url=metadata.thumb_url,
                    sha256=metadata.sha256,
                )

            try:
                response = await adapter.continue_after_actions(
                    previous=response,
                    action_results=results,
                    screenshot=screenshot,
                )
            except Exception as exc:
                await event_broker.publish(
                    session_id,
                    "error",
                    code="LLM_RESPONSE_ERROR",
                    message=_exception_message(exc),
                )
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="LLM call failed",
                    state="error",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return

        await event_broker.publish(
            session_id,
            "warning",
            code="MAX_STEPS_REACHED",
            message=f"Reached MAX_AGENT_STEPS={settings.max_agent_steps}",
        )
        await event_broker.publish(
            session_id,
            "task_status",
            label="Step limit reached",
            state="error",
            step=settings.max_agent_steps,
            max_steps=settings.max_agent_steps,
        )
    finally:
        await adapter.aclose()


def _http_client(settings: Settings):
    import httpx

    return httpx.AsyncClient(timeout=settings.action_timeout_sec + 5)
