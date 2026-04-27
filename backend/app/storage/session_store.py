from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from app.config import Settings
from app.schemas.sessions import SessionInfo


SESSION_SET_KEY = "opencau:sessions"


@dataclass(frozen=True)
class StoredSession:
    session_id: str
    status: str
    container_id: str | None
    vnc_url: str | None
    created_at: float
    updated_at: float
    last_active_at: float
    idle_deadline: float
    deleted_at: float | None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "StoredSession":
        return cls(
            session_id=str(data["session_id"]),
            status=str(data.get("status") or "missing"),
            container_id=data.get("container_id") or None,
            vnc_url=data.get("vnc_url") or None,
            created_at=float(data.get("created_at") or 0),
            updated_at=float(data.get("updated_at") or 0),
            last_active_at=float(data.get("last_active_at") or 0),
            idle_deadline=float(data.get("idle_deadline") or 0),
            deleted_at=float(data["deleted_at"]) if data.get("deleted_at") else None,
        )

    def to_session_info(self) -> SessionInfo:
        return SessionInfo(
            session_id=self.session_id,
            status=self.status,  # type: ignore[arg-type]
            container_id=self.container_id,
            vnc_url=self.vnc_url,
        )


def _session_key(session_id: str) -> str:
    return f"opencau:session:{session_id}"


def _string_mapping(data: dict[str, Any]) -> dict[str, str]:
    return {key: "" if value is None else str(value) for key, value in data.items()}


class RedisSessionManager:
    def __init__(self, settings: Settings, *, force_memory: bool = False) -> None:
        self._url = settings.redis_url
        self._idle_timeout_sec = settings.sandbox_idle_timeout_sec
        self._redis: Any | None = None
        self._force_memory = force_memory
        self._memory: dict[str, dict[str, str]] = {}

    @property
    def backend_name(self) -> str:
        return "redis" if self._redis is not None else "memory"

    @property
    def is_persistent_backend(self) -> bool:
        return self._redis is not None

    async def connect(self) -> None:
        if self._force_memory:
            return
        try:
            from redis import asyncio as redis_async
        except Exception:
            return
        try:
            client = redis_async.from_url(self._url, decode_responses=True)
            await client.ping()
        except Exception:
            return
        self._redis = client

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def upsert_session(self, session: SessionInfo, *, now: float | None = None) -> StoredSession:
        ts = now or time.time()
        existing = await self.get_session(session.session_id)
        created_at = existing.created_at if existing else ts
        record = {
            "session_id": session.session_id,
            "status": session.status,
            "container_id": session.container_id,
            "vnc_url": session.vnc_url,
            "created_at": created_at,
            "updated_at": ts,
            "last_active_at": ts,
            "idle_deadline": ts + self._idle_timeout_sec,
            "deleted_at": None,
        }
        await self._write(session.session_id, record)
        return StoredSession.from_mapping(record)

    async def touch(self, session_id: str, *, now: float | None = None) -> None:
        record = await self._read(session_id)
        if record is None or record.get("deleted_at"):
            return
        ts = now or time.time()
        record["updated_at"] = str(ts)
        record["last_active_at"] = str(ts)
        record["idle_deadline"] = str(ts + self._idle_timeout_sec)
        await self._write(session_id, record)

    async def mark_deleted(self, session_id: str, *, now: float | None = None) -> None:
        record = await self._read(session_id)
        ts = now or time.time()
        if record is None:
            record = {
                "session_id": session_id,
                "status": "missing",
                "container_id": None,
                "vnc_url": None,
                "created_at": ts,
                "updated_at": ts,
                "last_active_at": ts,
                "idle_deadline": ts,
            }
        record["status"] = "missing"
        record["updated_at"] = str(ts)
        record["deleted_at"] = str(ts)
        await self._write(session_id, record)

    async def delete(self, session_id: str) -> None:
        if self._redis is not None:
            await self._redis.delete(_session_key(session_id))
            await self._redis.srem(SESSION_SET_KEY, session_id)
            return
        self._memory.pop(session_id, None)

    async def get_session(self, session_id: str) -> StoredSession | None:
        record = await self._read(session_id)
        if record is None:
            return None
        return StoredSession.from_mapping(record)

    async def list_sessions(self, *, include_deleted: bool = False) -> list[StoredSession]:
        session_ids = await self._session_ids()
        sessions: list[StoredSession] = []
        for session_id in session_ids:
            session = await self.get_session(session_id)
            if session is None:
                continue
            if session.deleted_at is not None and not include_deleted:
                continue
            sessions.append(session)
        return sorted(sessions, key=lambda session: session.updated_at, reverse=True)

    async def active_session_ids(self) -> set[str]:
        return {session.session_id for session in await self.list_sessions()}

    async def expired_session_ids(self, *, now: float | None = None) -> list[str]:
        ts = now or time.time()
        expired: list[str] = []
        for session in await self.list_sessions():
            if session.idle_deadline <= ts:
                expired.append(session.session_id)
        return expired

    async def _session_ids(self) -> set[str]:
        if self._redis is not None:
            return set(await self._redis.smembers(SESSION_SET_KEY))
        return set(self._memory)

    async def _read(self, session_id: str) -> dict[str, str] | None:
        if self._redis is not None:
            record = await self._redis.hgetall(_session_key(session_id))
            return dict(record) if record else None
        record = self._memory.get(session_id)
        return dict(record) if record else None

    async def _write(self, session_id: str, data: dict[str, Any]) -> None:
        mapping = _string_mapping(data)
        if self._redis is not None:
            await self._redis.hset(_session_key(session_id), mapping=mapping)
            await self._redis.sadd(SESSION_SET_KEY, session_id)
            return
        self._memory[session_id] = mapping
