from __future__ import annotations

from app.config import Settings
from app.llm.base import ActionResult, AgentResponse, Screenshot


def system_instructions(settings: Settings, *, native_computer: bool) -> str:
    tool_name = "computer tool" if native_computer else "'computer' function tool"
    return (
        f"You operate a remote Ubuntu desktop sandbox via the {tool_name}. "
        "Use only GUI/browser actions; do not open terminals, do not ask for shell commands, "
        "and do not invent tools. Always inspect the most recent screenshot before acting. "
        "Describe only high-level intent in short Korean reasoning summaries when useful; "
        "never reveal hidden chain-of-thought. "
        f"The display is {settings.display_width}x{settings.display_height}, with (0,0) at the top-left. "
        "Click the visual center of targets, not the label, border, or top-left corner. "
        "The sandbox intentionally keeps the home desktop on a noexec mount, so do not use desktop .desktop launchers. "
        "To open Firefox, click the trusted bottom-panel browser launcher: the blue globe icon near the lower center, "
        "approximately (985,1053) on a 1920x1080 display. Do not click the blank desktop above the panel around y=970. "
        "Use one click, wait about 2000ms, then inspect a screenshot. "
        "If a screenshot does not change after an action, do not repeat that coordinate; choose a different target, "
        "use a double_click on the visual center, or report that the UI is not responding. "
        "For web navigation, open Firefox, focus the address bar with Ctrl+L when needed, type the full URL, "
        "press Return, wait, then inspect the screenshot. Finish without calling the tool when the task is done."
    )


def screen_feedback_text(
    *,
    previous: AgentResponse,
    action_results: list[ActionResult],
    screenshot: Screenshot,
) -> str:
    changed = previous.extra.get("last_screen_changed") if previous.extra else None
    unchanged_count = previous.extra.get("unchanged_screen_count") if previous.extra else None
    last_sha = screenshot.sha256[:12]
    result_lines = []
    for result in action_results:
        line = f"{result.action.type} status={result.status} duration_ms={result.duration_ms}"
        if result.error_code:
            line += f" error_code={result.error_code}"
        if result.message:
            line += f" message={result.message}"
        result_lines.append(line)
    parts = [
        "Updated screenshot after the computer actions.",
        f"Screenshot sha256 prefix: {last_sha}.",
    ]
    if result_lines:
        parts.append("Executed actions: " + "; ".join(result_lines) + ".")
    if changed is False:
        count_text = f" for {unchanged_count} consecutive visual step(s)" if unchanged_count else ""
        parts.append(
            "Important: the screenshot did not visually change"
            f"{count_text}. Do not repeat the same coordinate."
        )
        hint = _desktop_recovery_hint(action_results)
        if hint:
            parts.append(hint)
    elif changed is True:
        parts.append("The screenshot changed after the actions; continue from the new visible state.")
    if _pressed_return(action_results):
        parts.append(
            "If the requested page or result is now visible, finish with a concise final message instead of "
            "calling more computer actions."
        )
    return " ".join(parts)


def action_feedback_payload(
    *,
    previous: AgentResponse,
    action_results: list[ActionResult],
    screenshot: Screenshot,
) -> dict[str, object]:
    changed = previous.extra.get("last_screen_changed") if previous.extra else None
    unchanged_count = previous.extra.get("unchanged_screen_count") if previous.extra else None
    payload: dict[str, object] = {
        "status": "ok" if all(result.status == "ok" for result in action_results) else "partial",
        "screen_changed": changed,
        "unchanged_screen_count": unchanged_count,
        "screenshot_sha256": screenshot.sha256,
        "executed_actions": [
            {
                "type": result.action.type,
                "x": result.action.x,
                "y": result.action.y,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "error_code": result.error_code,
                "message": result.message,
            }
            for result in action_results
        ],
    }
    hint = _desktop_recovery_hint(action_results) if changed is False else None
    if hint:
        payload["recovery_hint"] = hint
    if _pressed_return(action_results):
        payload["navigation_hint"] = (
            "Return was pressed after navigation. If the requested page is visible in the screenshot, "
            "finish with a message instead of more tool calls."
        )
    return payload


def _pressed_return(action_results: list[ActionResult]) -> bool:
    for result in action_results:
        action = result.action
        if action.type == "keypress" and action.keys and any(key.lower() == "return" for key in action.keys):
            return True
    return False


def _desktop_recovery_hint(action_results: list[ActionResult]) -> str | None:
    for result in action_results:
        action = result.action
        if action.x is None or action.y is None:
            continue
        if 20 <= action.x <= 125 and 250 <= action.y <= 370:
            return (
                "The last click was near where the Home icon appears on legacy XFCE desktops, not the Firefox icon. "
                "Use the trusted bottom-panel browser launcher instead: click the blue globe icon near (985,1053), "
                "wait 2000ms, then inspect a screenshot."
            )
        if 20 <= action.x <= 125 and 30 <= action.y <= 130:
            return (
                "The last click was near a desktop launcher area. The sandbox home desktop is noexec, so desktop "
                ".desktop launchers can show trust dialogs. Use the trusted bottom-panel browser launcher near (985,1053)."
            )
        if 930 <= action.x <= 1040 and action.y >= 1010:
            return (
                "The last click was near the bottom browser launcher. If nothing changed, try a single click "
                "closer to the icon center, then wait 1500ms and inspect a screenshot."
            )
    return None
