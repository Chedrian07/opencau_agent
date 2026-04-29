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

NON_VISUAL_ACTION_TYPES = frozenset({"screenshot", "wait", "cursor_position"})
PANEL_SETTLE_SECONDS = 4.0
NAVIGATION_SETTLE_SECONDS = 3.0
BROWSER_TASK_TERMS = (
    "browser",
    "firefox",
    "http://",
    "https://",
    "navigate",
    "website",
    "web",
    ".com",
    ".net",
    ".org",
    "브라우저",
    "파이어폭스",
    "접속",
    "웹",
    "사이트",
)


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


def _has_visual_action(actions: list[Action]) -> bool:
    return any(action.type not in NON_VISUAL_ACTION_TYPES for action in actions)


def _needs_panel_settle(action: Action, settings: Settings) -> bool:
    if action.type not in {"click", "double_click"}:
        return False
    if action.x is None or action.y is None:
        return False
    panel_top = max(0, settings.display_height - 90)
    center = settings.display_width // 2
    return panel_top <= action.y <= settings.display_height - 1 and center - 250 <= action.x <= center + 250


def _trusted_browser_launcher_action(settings: Settings) -> Action:
    x = round(settings.display_width * 985 / 1920)
    y = round(settings.display_height * 1053 / 1080)
    return Action(type="click", x=x, y=min(y, settings.display_height - 1), button="left")


def _looks_like_browser_task(user_message: str) -> bool:
    lowered = user_message.lower()
    return any(term in lowered for term in BROWSER_TASK_TERMS)


def _looks_like_missed_browser_launcher(action: Action, settings: Settings) -> bool:
    if action.type not in {"click", "double_click"}:
        return False
    if action.x is None or action.y is None:
        return False
    if _needs_panel_settle(action, settings):
        return False
    top_application_menu = action.x <= 140 and action.y <= 90
    lower_blank_desktop = settings.display_height - 180 <= action.y < settings.display_height - 90
    legacy_desktop_launcher = 20 <= action.x <= 130 and 30 <= action.y <= 380
    return top_application_menu or lower_blank_desktop or legacy_desktop_launcher


def _assist_browser_launcher_actions(
    actions: list[Action],
    *,
    user_message: str,
    settings: Settings,
    panel_launcher_opened: bool,
) -> tuple[list[Action], str | None]:
    if panel_launcher_opened or not actions or not _looks_like_browser_task(user_message):
        return actions, None
    if not any(_looks_like_missed_browser_launcher(action, settings) for action in actions):
        return actions, None

    action = _trusted_browser_launcher_action(settings)
    message = (
        "Browser task launcher assist: replaced a likely missed desktop/menu click with the trusted "
        f"bottom-panel Firefox launcher at ({action.x},{action.y})."
    )
    return [action], message


async def _settle_after_actions(actions: list[Action], settings: Settings, is_interrupted: Callable[[], bool]) -> bool:
    settle_seconds = 0.0
    if any(_needs_panel_settle(action, settings) for action in actions):
        settle_seconds = max(settle_seconds, PANEL_SETTLE_SECONDS)
    if any(action.type == "keypress" and action.keys and "Return" in action.keys for action in actions):
        settle_seconds = max(settle_seconds, NAVIGATION_SETTLE_SECONDS)
    if settle_seconds <= 0:
        return False
    deadline = time.monotonic() + settle_seconds
    while time.monotonic() < deadline:
        if is_interrupted():
            return True
        await asyncio.sleep(0.1)
    return False


async def _capture_screenshot(
    deps: AgentLoopDeps,
    session_id: str,
    *,
    prefer_action_latest: bool = True,
) -> tuple[Screenshot | None, ScreenshotMetadata | None]:
    action_image = None
    if prefer_action_latest:
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

    await event_broker.publish(
        session_id,
        "task_status",
        label="Waiting for model",
        state="running",
        step=0,
        max_steps=settings.max_agent_steps,
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
    last_screenshot_sha = metadata.sha256 if metadata is not None else None
    unchanged_screen_count = 0
    panel_launcher_opened = False

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

            assisted_actions, assist_message = _assist_browser_launcher_actions(
                response.actions,
                user_message=user_message,
                settings=settings,
                panel_launcher_opened=panel_launcher_opened,
            )
            if assist_message is not None:
                response.actions = assisted_actions
                await event_broker.publish(
                    session_id,
                    "warning",
                    code="BROWSER_LAUNCHER_ASSIST",
                    message=assist_message,
                )

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
            executed_actions: list[Action] = []
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
                    if panel_launcher_opened and _needs_panel_settle(action, settings):
                        result = ActionResult(
                            action=action,
                            status="error",
                            duration_ms=0,
                            error_code="PANEL_LAUNCHER_ALREADY_USED",
                            message=(
                                "The browser launcher was already used and Firefox is open; "
                                "use Ctrl+L, type the URL, and press Return instead of opening another browser window."
                            ),
                        )
                        results.append(result)
                        await event_broker.publish(
                            session_id,
                            "warning",
                            code="PANEL_LAUNCHER_ALREADY_USED",
                            message=result.message,
                        )
                        await event_broker.publish(
                            session_id,
                            "action_executed",
                            action=_action_dump(action),
                            duration_ms=result.duration_ms,
                            status=result.status,
                            error_code=result.error_code,
                            message=result.message,
                        )
                        continue
                    result = await deps.action_executor.execute(
                        session_id=session_id, action=action, client=http
                    )
                    executed_actions.append(action)
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

            if await _settle_after_actions(executed_actions, settings, deps.is_interrupted):
                await event_broker.publish(
                    session_id,
                    "task_status",
                    label="Interrupted while waiting for UI",
                    state="interrupted",
                    step=step,
                    max_steps=settings.max_agent_steps,
                )
                return

            try:
                screenshot, metadata = await _capture_screenshot(deps, session_id, prefer_action_latest=False)
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
                previous_screenshot_sha = last_screenshot_sha
                await event_broker.publish(
                    session_id,
                    "screenshot",
                    url=metadata.url,
                    thumb_url=metadata.thumb_url,
                    sha256=metadata.sha256,
                )
                screen_changed = previous_screenshot_sha != metadata.sha256
                if _has_visual_action(response.actions) and not screen_changed:
                    unchanged_screen_count += 1
                else:
                    unchanged_screen_count = 0
                last_screenshot_sha = metadata.sha256
                response.extra["last_screen_changed"] = screen_changed
                response.extra["unchanged_screen_count"] = unchanged_screen_count
                response.extra["last_screenshot_sha"] = metadata.sha256
                if (
                    screen_changed
                    and any(_needs_panel_settle(action, settings) for action in executed_actions)
                    and all(result.status == "ok" for result in results)
                ):
                    panel_launcher_opened = True

                if unchanged_screen_count >= settings.repeated_action_threshold:
                    await event_broker.publish(
                        session_id,
                        "warning",
                        code="SCREEN_UNCHANGED",
                        message=(
                            "Screen did not change after "
                            f"{unchanged_screen_count} visual action steps; aborting loop"
                        ),
                    )
                    await event_broker.publish(
                        session_id,
                        "task_status",
                        label="Screen unchanged loop",
                        state="error",
                        step=step,
                        max_steps=settings.max_agent_steps,
                    )
                    return

            await event_broker.publish(
                session_id,
                "task_status",
                label="Waiting for model",
                state="running",
                step=step,
                max_steps=settings.max_agent_steps,
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
