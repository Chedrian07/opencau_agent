#!/usr/bin/env python3
"""Execute a single agent action inside the sandbox container.

Reads a JSON-encoded action from argv[1] and translates it into safe
xdotool/xclip/scrot subprocess calls. Returns a JSON result on stdout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any

ALLOWED_TYPES = {
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
}

XDOTOOL = "/usr/bin/xdotool"
XCLIP = "/usr/bin/xclip"
SCROT = "/usr/bin/scrot"

DEFAULT_DISPLAY = os.environ.get("DISPLAY", ":1")
DISPLAY_WIDTH = int(os.environ.get("DISPLAY_WIDTH", "1920"))
DISPLAY_HEIGHT = int(os.environ.get("DISPLAY_HEIGHT", "1080"))


def _run(cmd: list[str], *, timeout: float = 10.0, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.setdefault("DISPLAY", DEFAULT_DISPLAY)
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        timeout=timeout,
        input=input_bytes,
        env=env,
    )


def _coords(action: dict[str, Any]) -> tuple[int, int]:
    x = int(action["x"])
    y = int(action["y"])
    if not 0 <= x < DISPLAY_WIDTH or not 0 <= y < DISPLAY_HEIGHT:
        raise ValueError(f"coordinate ({x},{y}) out of display bounds")
    return x, y


def _xdotool_button(button: str | None) -> str:
    mapping = {"left": "1", "middle": "2", "right": "3", "wheel": "4", "back": "8", "forward": "9"}
    if button is None:
        return "1"
    if button not in mapping:
        raise ValueError(f"unsupported mouse button: {button}")
    return mapping[button]


def do_screenshot(_: dict[str, Any]) -> dict[str, Any]:
    out_path = "/tmp/opencau-action.png"
    _run([SCROT, "--overwrite", out_path], timeout=10)
    return {"output": out_path}


def do_click(action: dict[str, Any]) -> dict[str, Any]:
    x, y = _coords(action)
    button = _xdotool_button(action.get("button"))
    _run([XDOTOOL, "mousemove", "--sync", str(x), str(y), "click", button])
    return {"output": f"click {button} at {x},{y}"}


def do_double_click(action: dict[str, Any]) -> dict[str, Any]:
    x, y = _coords(action)
    _run([XDOTOOL, "mousemove", "--sync", str(x), str(y), "click", "--repeat", "2", "--delay", "60", "1"])
    return {"output": f"double_click at {x},{y}"}


def do_right_click(action: dict[str, Any]) -> dict[str, Any]:
    x, y = _coords(action)
    _run([XDOTOOL, "mousemove", "--sync", str(x), str(y), "click", "3"])
    return {"output": f"right_click at {x},{y}"}


def do_move(action: dict[str, Any]) -> dict[str, Any]:
    x, y = _coords(action)
    _run([XDOTOOL, "mousemove", "--sync", str(x), str(y)])
    return {"output": f"move to {x},{y}"}


def do_drag(action: dict[str, Any]) -> dict[str, Any]:
    path = action.get("path") or []
    if len(path) < 2:
        raise ValueError("drag requires at least 2 path points")
    points: list[tuple[int, int]] = []
    for raw in path:
        px = int(raw["x"])
        py = int(raw["y"])
        if not 0 <= px < DISPLAY_WIDTH or not 0 <= py < DISPLAY_HEIGHT:
            raise ValueError(f"drag point ({px},{py}) out of display bounds")
        points.append((px, py))
    start_x, start_y = points[0]
    _run([XDOTOOL, "mousemove", "--sync", str(start_x), str(start_y)])
    _run([XDOTOOL, "mousedown", "1"])
    try:
        for px, py in points[1:]:
            _run([XDOTOOL, "mousemove", "--sync", str(px), str(py)])
            time.sleep(0.02)
    finally:
        _run([XDOTOOL, "mouseup", "1"])
    return {"output": f"drag with {len(points)} points"}


def do_type(action: dict[str, Any]) -> dict[str, Any]:
    text = str(action.get("text") or "")
    if not text:
        raise ValueError("type requires text")
    is_ascii = all(ord(ch) < 128 for ch in text)
    if is_ascii and len(text) <= 2000:
        _run([XDOTOOL, "type", "--clearmodifiers", "--delay", "5", text], timeout=20)
    else:
        env = os.environ.copy()
        env.setdefault("DISPLAY", DEFAULT_DISPLAY)
        proc = subprocess.Popen(
            [XCLIP, "-selection", "clipboard"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        try:
            assert proc.stdin is not None
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
            time.sleep(0.12)
            _run([XDOTOOL, "key", "--clearmodifiers", "ctrl+v"], timeout=5)
            time.sleep(0.05)
        finally:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
    return {"output": f"typed {len(text)} chars"}


def do_keypress(action: dict[str, Any]) -> dict[str, Any]:
    keys = action.get("keys") or []
    if not isinstance(keys, list) or not keys:
        raise ValueError("keypress requires non-empty keys list")
    chord = "+".join(str(k) for k in keys)
    _run([XDOTOOL, "key", "--clearmodifiers", chord])
    return {"output": f"keypress {chord}"}


def do_scroll(action: dict[str, Any]) -> dict[str, Any]:
    x, y = _coords(action)
    _run([XDOTOOL, "mousemove", "--sync", str(x), str(y)])
    scroll_x = int(action.get("scroll_x") or 0)
    scroll_y = int(action.get("scroll_y") or 0)
    if scroll_y == 0 and scroll_x == 0:
        raise ValueError("scroll requires scroll_x or scroll_y")
    if scroll_y != 0:
        button = "5" if scroll_y > 0 else "4"
        clicks = min(abs(scroll_y), 100)
        for _ in range(max(clicks, 1)):
            _run([XDOTOOL, "click", button])
    if scroll_x != 0:
        button = "7" if scroll_x > 0 else "6"
        clicks = min(abs(scroll_x), 100)
        for _ in range(max(clicks, 1)):
            _run([XDOTOOL, "click", button])
    return {"output": f"scroll dx={scroll_x} dy={scroll_y}"}


def do_wait(action: dict[str, Any]) -> dict[str, Any]:
    duration_ms = int(action.get("duration_ms") or 0)
    if duration_ms <= 0:
        raise ValueError("wait requires duration_ms > 0")
    duration_ms = min(duration_ms, 30000)
    time.sleep(duration_ms / 1000.0)
    return {"output": f"waited {duration_ms}ms"}


def do_cursor_position(_: dict[str, Any]) -> dict[str, Any]:
    completed = _run([XDOTOOL, "getmouselocation", "--shell"])
    raw = completed.stdout.decode("utf-8", errors="replace").strip()
    info: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    return {"output": raw, "x": int(info.get("X", "0")), "y": int(info.get("Y", "0"))}


HANDLERS = {
    "screenshot": do_screenshot,
    "click": do_click,
    "double_click": do_double_click,
    "right_click": do_right_click,
    "move": do_move,
    "drag": do_drag,
    "type": do_type,
    "keypress": do_keypress,
    "scroll": do_scroll,
    "wait": do_wait,
    "cursor_position": do_cursor_position,
}


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"status": "error", "code": "USAGE", "message": "expected one JSON argument"}))
        return 2
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "code": "BAD_JSON", "message": str(exc)}))
        return 2
    if not isinstance(payload, dict):
        print(json.dumps({"status": "error", "code": "BAD_PAYLOAD", "message": "action must be an object"}))
        return 2
    action_type = payload.get("type")
    if action_type not in ALLOWED_TYPES:
        print(json.dumps({"status": "error", "code": "BAD_ACTION_TYPE", "message": f"unsupported type: {action_type}"}))
        return 2
    handler = HANDLERS[action_type]
    started = time.monotonic()
    try:
        result = handler(payload)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")[:2000]
        print(json.dumps({
            "status": "error",
            "code": "ACTION_FAILED",
            "message": stderr or str(exc),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }))
        return 1
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({
            "status": "error",
            "code": "ACTION_TIMEOUT",
            "message": str(exc),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }))
        return 1
    except ValueError as exc:
        print(json.dumps({
            "status": "error",
            "code": "ACTION_VALIDATION",
            "message": str(exc),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }))
        return 2
    duration_ms = int((time.monotonic() - started) * 1000)
    response = {"status": "ok", "duration_ms": duration_ms, **result}
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
