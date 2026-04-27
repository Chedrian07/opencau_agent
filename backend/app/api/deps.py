from __future__ import annotations

from fastapi import Request

from app.config import get_settings
from app.storage.session_store import RedisSessionManager
from app.storage.sqlite import SQLiteStore


def _sqlite_store() -> SQLiteStore:
    store = SQLiteStore(get_settings().sqlite_path)
    store.initialize()
    return store


async def _session_manager() -> RedisSessionManager:
    manager = RedisSessionManager(get_settings(), force_memory=True)
    await manager.connect()
    return manager


def get_sqlite_store(request: Request) -> SQLiteStore:
    store = getattr(request.app.state, "sqlite_store", None)
    if isinstance(store, SQLiteStore):
        return store
    return _sqlite_store()


async def get_session_manager(request: Request) -> RedisSessionManager:
    manager = getattr(request.app.state, "session_manager", None)
    if isinstance(manager, RedisSessionManager):
        return manager
    return await _session_manager()
