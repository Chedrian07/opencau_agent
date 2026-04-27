from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse

from app.agent.events import event_broker
from app.agent.runtime import agent_runtime
from app.api.deps import get_session_manager, get_sqlite_store
from app.config import Settings, get_settings
from app.sandbox.client import SandboxClient
from app.schemas.messages import UserMessageRequest, UserMessageResponse
from app.schemas.sessions import SESSION_ID_PATTERN
from app.storage.session_store import RedisSessionManager
from app.storage.sqlite import SQLiteStore
from app.storage.screenshot_store import ScreenshotStore

router = APIRouter(tags=["events"])
ws_router = APIRouter(tags=["events"])
SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]


def get_sandbox_client(settings: Settings = Depends(get_settings)) -> SandboxClient:
    return SandboxClient(settings)


def get_screenshot_store(settings: Settings = Depends(get_settings)) -> ScreenshotStore:
    return ScreenshotStore(settings.screenshot_dir)


@router.post("/sessions/{session_id}/messages", response_model=UserMessageResponse)
async def create_message(
    session_id: SessionId,
    request: UserMessageRequest,
    sandbox_client: SandboxClient = Depends(get_sandbox_client),
    screenshot_store: ScreenshotStore = Depends(get_screenshot_store),
    session_manager: RedisSessionManager = Depends(get_session_manager),
    sqlite_store: SQLiteStore = Depends(get_sqlite_store),
) -> UserMessageResponse:
    sqlite_store.record_message(session_id=session_id, role="user", text=request.text)
    await session_manager.touch(session_id)
    accepted = await agent_runtime.submit(
        session_id=session_id,
        text=request.text,
        sandbox_client=sandbox_client,
        screenshot_store=screenshot_store,
        sqlite_store=sqlite_store,
        session_manager=session_manager,
    )
    return UserMessageResponse(session_id=session_id, accepted=accepted)


@router.post("/sessions/{session_id}/interrupt", status_code=status.HTTP_202_ACCEPTED)
async def interrupt_session(session_id: SessionId) -> dict[str, bool]:
    await agent_runtime.interrupt(session_id)
    return {"accepted": True}


@router.get("/sessions/{session_id}/events")
async def list_session_events(session_id: SessionId) -> list[dict[str, object]]:
    return await event_broker.history(session_id)


@router.get("/sessions/{session_id}/screenshots/{shot_id}.png")
async def get_screenshot(
    session_id: SessionId,
    shot_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    screenshot_store: ScreenshotStore = Depends(get_screenshot_store),
) -> FileResponse:
    path = screenshot_store.path_for(session_id, shot_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "SCREENSHOT_NOT_FOUND"})
    return FileResponse(path, media_type="image/png")


@router.get("/sessions/{session_id}/screenshots/{shot_id}.webp")
async def get_screenshot_thumb(
    session_id: SessionId,
    shot_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    screenshot_store: ScreenshotStore = Depends(get_screenshot_store),
) -> FileResponse:
    path = screenshot_store.thumb_path_for(session_id, shot_id)
    if not path.is_file():
        path = screenshot_store.path_for(session_id, shot_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail={"code": "SCREENSHOT_NOT_FOUND"})
        return FileResponse(path, media_type="image/png")
    return FileResponse(path, media_type="image/webp")


@ws_router.websocket("/ws/sessions/{session_id}/events")
async def stream_session_events(websocket: WebSocket, session_id: SessionId) -> None:
    await websocket.accept()
    try:
        async for event in event_broker.subscribe(session_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
