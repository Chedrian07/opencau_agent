from collections.abc import Iterator
from contextlib import contextmanager
import json
import time
from typing import Any

import docker
from docker.errors import NotFound
from docker.models.containers import Container

from app.commands import (
    READ_LATEST_SCREENSHOT_COMMAND,
    READ_SCREENSHOT_COMMAND,
    agent_action_command,
    command_for,
)
from app.config import Settings
from app.schemas import (
    ActionRequest,
    ActionResponse,
    CommandRequest,
    CommandResult,
    SessionResponse,
)

LABEL_ROLE = "opencau.role"
LABEL_SESSION = "opencau.session_id"
SANDBOX_ROLE = "sandbox"


class SandboxStartupError(RuntimeError):
    pass


def container_name(session_id: str) -> str:
    return f"opencau-sandbox-{session_id}"


@contextmanager
def docker_client() -> Iterator[docker.DockerClient]:
    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


def _session_response(session_id: str, container: Container | None) -> SessionResponse:
    if container is None:
        return SessionResponse(session_id=session_id, status="missing")
    container.reload()
    status = "running" if container.status == "running" else "stopped"
    return SessionResponse(
        session_id=session_id,
        status=status,
        container_id=container.id,
        container_name=container.name,
    )


def _find_container(client: docker.DockerClient, session_id: str) -> Container | None:
    try:
        return client.containers.get(container_name(session_id))
    except NotFound:
        return None


def _sandbox_containers(client: docker.DockerClient) -> list[Container]:
    return client.containers.list(all=True, filters={"label": [f"{LABEL_ROLE}={SANDBOX_ROLE}"]})


def _wait_until_ready(container: Container, timeout_sec: int) -> bool:
    deadline = time.monotonic() + timeout_sec
    healthcheck = command_for(CommandRequest(operation="healthcheck"))
    while time.monotonic() < deadline:
        container.reload()
        if container.status != "running":
            return False
        result = container.exec_run(healthcheck)
        if result.exit_code == 0:
            return True
        time.sleep(0.5)
    return False


def create_sandbox(settings: Settings, session_id: str) -> SessionResponse:
    with docker_client() as client:
        existing = _find_container(client, session_id)
        if existing is not None:
            return _session_response(session_id, existing)

        host_config: dict[str, Any] = {
            "network": settings.sandbox_network,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "read_only": True,
            "tmpfs": {
                "/tmp": "rw,nosuid,nodev,size=512m,mode=1777",
                "/run/user/1200": "rw,nosuid,nodev,size=128m,uid=1200,gid=1200,mode=0700",
                "/var/tmp": "rw,nosuid,nodev,size=256m,uid=1200,gid=1200,mode=1777",
                "/home/agent": "rw,nosuid,nodev,size=512m,uid=1200,gid=1200,mode=0700",
            },
            "mem_limit": settings.sandbox_memory_limit,
            "nano_cpus": int(settings.sandbox_cpus * 1_000_000_000),
            "pids_limit": settings.sandbox_pids_limit,
            "init": True,
            "detach": True,
            "labels": {
                LABEL_ROLE: SANDBOX_ROLE,
                LABEL_SESSION: session_id,
            },
            "environment": {
                "DISPLAY": ":1",
                "DISPLAY_WIDTH": str(settings.display_width),
                "DISPLAY_HEIGHT": str(settings.display_height),
                "DISPLAY_DEPTH": str(settings.display_depth),
            },
            "name": container_name(session_id),
        }
        container = client.containers.run(settings.sandbox_image, **host_config)
        if not _wait_until_ready(container, settings.sandbox_start_timeout_sec):
            container.remove(force=True)
            raise SandboxStartupError(f"sandbox {session_id} did not become ready")
        return _session_response(session_id, container)


def inspect_sandbox(session_id: str) -> SessionResponse:
    with docker_client() as client:
        return _session_response(session_id, _find_container(client, session_id))


def list_sandboxes() -> list[SessionResponse]:
    with docker_client() as client:
        responses: list[SessionResponse] = []
        for container in _sandbox_containers(client):
            session_id = container.labels.get(LABEL_SESSION)
            if session_id:
                responses.append(_session_response(session_id, container))
        return sorted(responses, key=lambda item: item.session_id)


def delete_sandbox(session_id: str) -> None:
    with docker_client() as client:
        container = _find_container(client, session_id)
        if container is None:
            return
        container.remove(force=True)


def run_allowed_command(session_id: str, request: CommandRequest) -> CommandResult:
    command = command_for(request)
    with docker_client() as client:
        container = _find_container(client, session_id)
        if container is None:
            return CommandResult(
                operation=request.operation,
                exit_code=127,
                stderr="sandbox session not found",
            )
        result = container.exec_run(command, demux=True)
        stdout_raw, stderr_raw = result.output or (b"", b"")
        return CommandResult(
            operation=request.operation,
            exit_code=result.exit_code,
            stdout=(stdout_raw or b"").decode("utf-8", errors="replace")[:8000],
            stderr=(stderr_raw or b"").decode("utf-8", errors="replace")[:8000],
        )


def capture_screenshot_png(session_id: str) -> bytes | None:
    command = command_for(CommandRequest(operation="screenshot"))
    with docker_client() as client:
        container = _find_container(client, session_id)
        if container is None:
            return None
        result = container.exec_run(command)
        if result.exit_code != 0:
            return None
        read_result = container.exec_run(READ_SCREENSHOT_COMMAND)
        if read_result.exit_code != 0 or not read_result.output:
            return None
        return bytes(read_result.output)


def execute_action(session_id: str, request: ActionRequest) -> ActionResponse:
    payload = request.model_dump(exclude_none=True)
    command = agent_action_command(json.dumps(payload, separators=(",", ":")))
    with docker_client() as client:
        container = _find_container(client, session_id)
        if container is None:
            return ActionResponse(
                status="error",
                duration_ms=0,
                error_code="SANDBOX_NOT_FOUND",
                message=f"sandbox session {session_id} is not running",
            )
        result = container.exec_run(command, demux=False)
        raw = (result.output or b"").decode("utf-8", errors="replace").strip()
        parsed: dict[str, Any] | None = None
        if raw:
            try:
                parsed = json.loads(raw.splitlines()[-1])
            except json.JSONDecodeError:
                parsed = None
        if parsed is None:
            return ActionResponse(
                status="error",
                duration_ms=0,
                error_code="ACTION_PARSE_ERROR",
                message=raw[:1000] if raw else f"exit_code={result.exit_code}",
            )
        status = parsed.get("status", "error")
        duration_ms = int(parsed.get("duration_ms", 0))
        return ActionResponse(
            status="ok" if status == "ok" else "error",
            duration_ms=max(duration_ms, 0),
            output=str(parsed.get("output", ""))[:4000],
            error_code=parsed.get("code") if status != "ok" else None,
            message=parsed.get("message") if status != "ok" else None,
            extra={k: v for k, v in parsed.items() if k not in {"status", "duration_ms", "output", "code", "message"}} or None,
        )


def capture_latest_action_screenshot(session_id: str) -> bytes | None:
    with docker_client() as client:
        container = _find_container(client, session_id)
        if container is None:
            return None
        result = container.exec_run(READ_LATEST_SCREENSHOT_COMMAND)
        if result.exit_code != 0 or not result.output:
            return None
        return bytes(result.output)


def sandbox_host(session_id: str) -> str | None:
    response = inspect_sandbox(session_id)
    if response.status == "missing" or response.container_name is None:
        return None
    return response.container_name
