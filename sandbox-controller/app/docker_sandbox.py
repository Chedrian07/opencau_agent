from collections.abc import Iterator
from contextlib import contextmanager
import time
from typing import Any

import docker
from docker.errors import NotFound
from docker.models.containers import Container

from app.commands import READ_SCREENSHOT_COMMAND, command_for
from app.config import Settings
from app.schemas import CommandRequest, CommandResult, SessionResponse

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


def sandbox_host(session_id: str) -> str | None:
    response = inspect_sandbox(session_id)
    if response.status == "missing" or response.container_name is None:
        return None
    return response.container_name
