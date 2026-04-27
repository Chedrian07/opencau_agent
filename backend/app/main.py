from contextlib import asynccontextmanager, suppress
import asyncio
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.events import event_broker
from app.api import events, health, preflight, sessions, vnc_proxy
from app.config import get_settings
from app.sandbox.client import SandboxClient
from app.storage.screenshot_store import ScreenshotStore
from app.storage.session_store import RedisSessionManager
from app.storage.sqlite import SQLiteStore


async def _cleanup_once(
    *,
    settings,
    session_manager: RedisSessionManager,
    sqlite_store: SQLiteStore,
    sandbox_client: SandboxClient,
    screenshot_store: ScreenshotStore,
) -> None:
    expired_session_ids = await session_manager.expired_session_ids()
    for session_id in expired_session_ids:
        with suppress(Exception):
            await sandbox_client.delete_session(session_id)
        await session_manager.mark_deleted(session_id)
        sqlite_store.mark_session_deleted(session_id)

    cutoff = time.time() - (settings.screenshot_retention_hours * 3600)
    paths = sqlite_store.delete_screenshots_older_than(cutoff)
    screenshot_store.remove_paths(paths)


async def _cleanup_loop(
    *,
    settings,
    session_manager: RedisSessionManager,
    sqlite_store: SQLiteStore,
    sandbox_client: SandboxClient,
    screenshot_store: ScreenshotStore,
) -> None:
    while True:
        with suppress(Exception):
            await _cleanup_once(
                settings=settings,
                session_manager=session_manager,
                sqlite_store=sqlite_store,
                sandbox_client=sandbox_client,
                screenshot_store=screenshot_store,
            )
        await asyncio.sleep(settings.cleanup_interval_sec)


async def _reconcile_orphan_sandboxes(settings, session_manager: RedisSessionManager) -> None:
    if not session_manager.is_persistent_backend:
        return
    sandbox_client = SandboxClient(settings)
    active_session_ids = await session_manager.active_session_ids()
    with suppress(Exception):
        controller_sessions = await sandbox_client.list_sessions()
        for session in controller_sessions:
            if session.session_id not in active_session_ids:
                await sandbox_client.delete_session(session.session_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    sqlite_store = SQLiteStore(settings.sqlite_path)
    sqlite_store.initialize()
    session_manager = RedisSessionManager(settings)
    await session_manager.connect()
    event_broker.configure_persistence(sqlite_store)
    event_broker.configure_session_store(session_manager)
    await _reconcile_orphan_sandboxes(settings, session_manager)

    sandbox_client = SandboxClient(settings)
    screenshot_store = ScreenshotStore(settings.screenshot_dir)
    cleanup_task = asyncio.create_task(
        _cleanup_loop(
            settings=settings,
            session_manager=session_manager,
            sqlite_store=sqlite_store,
            sandbox_client=sandbox_client,
            screenshot_store=screenshot_store,
        )
    )
    app.state.sqlite_store = sqlite_store
    app.state.session_manager = session_manager
    app.state.cleanup_task = cleanup_task
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        event_broker.configure_persistence(None)
        event_broker.configure_session_store(None)
        await session_manager.aclose()


app = FastAPI(title="OpenCAU Agent Backend", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["content-type"],
)

app.include_router(health.router, prefix="/api")
app.include_router(preflight.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(events.ws_router)
app.include_router(vnc_proxy.router)
