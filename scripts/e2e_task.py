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

        while time.monotonic() < deadline:
            events = request_json("GET", f"/api/sessions/{session_id}/events")
            task_events = [event for event in events if event.get("type") == "task_status"]
            if task_events and task_events[-1].get("state") in {"done", "error", "interrupted"}:
                break
            time.sleep(1.0)
        else:
            raise TimeoutError(f"no terminal task_status after {TIMEOUT_SEC}s; tail={event_tail(events)}")

        task_events = [event for event in events if event.get("type") == "task_status"]
        terminal = task_events[-1]
        if terminal.get("state") != "done":
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
                    "terminal_state": terminal["state"],
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
