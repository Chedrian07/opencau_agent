#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
PROMPT = os.environ.get(
    "E2E_PROMPT",
    "Open Firefox and navigate to https://example.com. Stop when the page is visible.",
)
TIMEOUT_SEC = float(os.environ.get("E2E_TIMEOUT_SEC", "300"))
EXPECTED_WINDOW_TITLE = os.environ.get("E2E_EXPECT_WINDOW_TITLE", "Example Domain").strip()


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        method=method,
        headers={"content-type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status == 204:
            return None
        return json.loads(response.read().decode("utf-8"))


def event_tail(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tail: list[dict[str, Any]] = []
    for event in events[-8:]:
        tail.append(
            {
                key: event.get(key)
                for key in ("type", "sequence", "state", "label", "code", "message")
                if key in event
            }
        )
    return tail


def maybe_active_window_title(session_id: str) -> str | None:
    if not EXPECTED_WINDOW_TITLE:
        return None
    try:
        result = request_json("POST", f"/api/sessions/{session_id}/smoke", {"operation": "active_window_title"})
    except Exception:
        return None
    if result.get("exit_code") != 0:
        return None
    title = str(result.get("stdout") or "").strip()
    if EXPECTED_WINDOW_TITLE.lower() in title.lower():
        return title
    return None


def main() -> int:
    session_id = f"e2e-real-{uuid.uuid4().hex[:10]}"
    deleted = False
    deadline = time.monotonic() + TIMEOUT_SEC
    events: list[dict[str, Any]] = []

    try:
        health = request_json("GET", "/api/health")
        request_json("POST", "/api/sessions", {"session_id": session_id})
        accepted = request_json("POST", f"/api/sessions/{session_id}/messages", {"text": PROMPT})
        if not accepted.get("accepted"):
            raise RuntimeError(f"message was not accepted: {accepted}")

        observed_title: str | None = None
        next_title_probe = 0.0
        while time.monotonic() < deadline:
            events = request_json("GET", f"/api/sessions/{session_id}/events")
            now = time.monotonic()
            if now >= next_title_probe:
                next_title_probe = now + 2.0
                observed_title = maybe_active_window_title(session_id)
                if observed_title:
                    break
            task_events = [event for event in events if event.get("type") == "task_status"]
            if task_events and task_events[-1].get("state") in {"done", "error", "interrupted"}:
                break
            time.sleep(1.0)
        else:
            raise TimeoutError(f"no terminal task_status after {TIMEOUT_SEC}s; tail={event_tail(events)}")

        task_events = [event for event in events if event.get("type") == "task_status"]
        terminal = task_events[-1] if task_events else None
        if observed_title is None:
            observed_title = maybe_active_window_title(session_id)
        if terminal is None and observed_title is None:
            raise RuntimeError(f"no task_status was emitted; tail={event_tail(events)}")
        if observed_title is None and terminal is not None and terminal.get("state") != "done":
            raise RuntimeError(f"terminal state was not done: {terminal}; tail={event_tail(events)}")
        if not any(event.get("type") == "screenshot" for event in events):
            raise RuntimeError("no screenshot event was emitted")

        request_json("DELETE", f"/api/sessions/{session_id}")
        deleted = True
        print(
            json.dumps(
                {
                    "status": "ok",
                    "session_id": session_id,
                    "events": len(events),
                    "terminal_state": "observed" if observed_title is not None else terminal["state"],
                    "observed_window_title": observed_title,
                    "profile": health.get("llm", {}).get("profile"),
                    "model": health.get("llm", {}).get("model"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        print(f"E2E task failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if not deleted:
            try:
                request_json("DELETE", f"/api/sessions/{session_id}")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
