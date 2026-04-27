from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from httpx import HTTPError

from app.agent.events import event_broker
from app.agent.runtime import agent_runtime
from app.api.deps import get_session_manager, get_sqlite_store
from app.config import Settings, get_settings
from app.sandbox.client import SandboxClient
from app.schemas.sessions import (
    SESSION_ID_PATTERN,
    CommandSmokeRequest,
    CommandSmokeResult,
    CreateSessionRequest,
    SessionInfo,
)
from app.storage.session_store import RedisSessionManager
from app.storage.sqlite import SQLiteStore

router = APIRouter(prefix="/sessions", tags=["sessions"])
SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]


def get_sandbox_client(settings: Settings = Depends(get_settings)) -> SandboxClient:
    return SandboxClient(settings)


@router.post("", response_model=SessionInfo, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
    session_manager: RedisSessionManager = Depends(get_session_manager),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
) -> SessionInfo:
    try:
        session = await sandbox_client.create_session(request.session_id)
        sqlite_store.clear_session_history(session.session_id)
        await event_broker.clear(session.session_id)
        await session_manager.upsert_session(session)
        sqlite_store.record_session(session)
        await event_broker.publish(session.session_id, "session_created")
        return session
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_CONTROLLER_ERROR"}) from exc


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: SessionId,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
    session_manager: RedisSessionManager = Depends(get_session_manager),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
) -> SessionInfo:
    try:
        session = await sandbox_client.get_session(session_id)
        if session.status == "missing":
            await session_manager.mark_deleted(session_id)
            sqlite_store.mark_session_deleted(session_id)
        else:
            await session_manager.upsert_session(session)
            sqlite_store.record_session(session)
        return session
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_CONTROLLER_ERROR"}) from exc


@router.get("", response_model=list[SessionInfo])
async def list_sessions(
    session_manager: RedisSessionManager = Depends(get_session_manager),
) -> list[SessionInfo]:
    return [session.to_session_info() for session in await session_manager.list_sessions()]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: SessionId,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
    session_manager: RedisSessionManager = Depends(get_session_manager),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
) -> None:
    try:
        await agent_runtime.interrupt(session_id)
        await sandbox_client.delete_session(session_id)
        await session_manager.mark_deleted(session_id)
        sqlite_store.mark_session_deleted(session_id)
        await event_broker.clear(session_id)
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
