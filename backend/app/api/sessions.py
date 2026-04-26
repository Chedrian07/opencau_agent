from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from httpx import HTTPError

from app.config import Settings, get_settings
from app.sandbox.client import SandboxClient
from app.schemas.sessions import (
    SESSION_ID_PATTERN,
    CommandSmokeRequest,
    CommandSmokeResult,
    CreateSessionRequest,
    SessionInfo,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]


def get_sandbox_client(settings: Settings = Depends(get_settings)) -> SandboxClient:
    return SandboxClient(settings)


@router.post("", response_model=SessionInfo, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
) -> SessionInfo:
    try:
        return await sandbox_client.create_session(request.session_id)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_CONTROLLER_ERROR"}) from exc


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: SessionId,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
) -> SessionInfo:
    try:
        return await sandbox_client.get_session(session_id)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_CONTROLLER_ERROR"}) from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: SessionId,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
) -> None:
    try:
        await sandbox_client.delete_session(session_id)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_CONTROLLER_ERROR"}) from exc


@router.post("/{session_id}/smoke", response_model=CommandSmokeResult)
async def run_smoke(
    session_id: SessionId,
    request: CommandSmokeRequest,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
) -> CommandSmokeResult:
    try:
        return await sandbox_client.run_smoke_command(session_id, request.operation)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_CONTROLLER_ERROR"}) from exc
