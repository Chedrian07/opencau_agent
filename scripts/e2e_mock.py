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
TIMEOUT_SEC = float(os.environ.get("E2E_TIMEOUT_SEC", "90"))


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        method=method,
        headers={"content-type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status == 204:
            return None
        return json.loads(response.read().decode("utf-8"))


def request_bytes(path: str) -> bytes:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=15) as response:
        return response.read()


def main() -> int:
    session_id = f"e2e-{uuid.uuid4().hex[:12]}"
    deadline = time.monotonic() + TIMEOUT_SEC
    deleted = False

    try:
        health = request_json("GET", "/api/health")
        if health.get("status") != "ok":
            raise RuntimeError(f"backend health is not ok: {health}")

        session = request_json("POST", "/api/sessions", {"session_id": session_id})
        if session.get("session_id") != session_id or session.get("status") != "running":
            raise RuntimeError(f"session did not start: {session}")

        accepted = request_json(
            "POST",
            f"/api/sessions/{session_id}/messages",
            {"text": "Run the mock E2E path and report completion."},
        )
        if not accepted.get("accepted"):
            raise RuntimeError(f"message was not accepted: {accepted}")

        events: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            events = request_json("GET", f"/api/sessions/{session_id}/events")
            states = [event for event in events if event.get("type") == "task_status"]
            if states and states[-1].get("state") in {"done", "error", "interrupted"}:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError(f"no terminal task_status after {TIMEOUT_SEC}s")

        types = {event.get("type") for event in events}
        required = {"session_created", "screenshot", "tool_call", "action_executed", "agent_message"}
        missing = sorted(required - types)
        if missing:
            raise RuntimeError(f"missing event types: {missing}")

        terminal = [event for event in events if event.get("type") == "task_status"][-1]
        if terminal.get("state") != "done":
            raise RuntimeError(f"task did not finish cleanly: {terminal}")

        screenshot = next(event for event in events if event.get("type") == "screenshot")
        image = request_bytes(str(screenshot["url"]))
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("screenshot endpoint did not return a PNG")

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
                    "storage": health.get("storage", {}),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        print(f"E2E failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if not deleted:
            try:
                request_json("DELETE", f"/api/sessions/{session_id}")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
