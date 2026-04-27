from collections import defaultdict, deque
from collections.abc import AsyncIterator
import asyncio
import time
from typing import Any, Protocol

from pydantic import TypeAdapter

from app.schemas.events import AgentEvent

MAX_EVENT_HISTORY = 200
EVENT_ADAPTER = TypeAdapter(AgentEvent)


class EventStore(Protocol):
    def record_event(self, event: dict[str, Any]) -> None: ...

    def list_events(self, session_id: str, *, limit: int = MAX_EVENT_HISTORY) -> list[dict[str, Any]]: ...


class SessionTouchStore(Protocol):
    async def touch(self, session_id: str) -> None: ...


class SessionEventBroker:
    def __init__(self) -> None:
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=MAX_EVENT_HISTORY))
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._event_store: EventStore | None = None
        self._session_store: SessionTouchStore | None = None

    def configure_persistence(self, event_store: EventStore | None) -> None:
        self._event_store = event_store

    def configure_session_store(self, session_store: SessionTouchStore | None) -> None:
        self._session_store = session_store

    async def publish(self, session_id: str, event_type: str, **payload: Any) -> dict[str, Any]:
        async with self._lock:
            self._sequences[session_id] += 1
            event = {
                "type": event_type,
                "session_id": session_id,
                "ts": time.time(),
                "sequence": self._sequences[session_id],
                **payload,
            }
            EVENT_ADAPTER.validate_python(event)
            self._history[session_id].append(event)
            subscribers = list(self._subscribers[session_id])

        if self._event_store is not None:
            try:
                self._event_store.record_event(event)
            except Exception:
                pass
        if self._session_store is not None:
            try:
                await self._session_store.touch(session_id)
            except Exception:
                pass

        for queue in subscribers:
            queue.put_nowait(event)
        return event

    async def subscribe(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            replay = await self._history_for(session_id)
            self._subscribers[session_id].add(queue)

        try:
            for event in replay:
                yield event
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers[session_id].discard(queue)

    async def history(self, session_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return await self._history_for(session_id)

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._history.pop(session_id, None)
            self._sequences.pop(session_id, None)

    async def _history_for(self, session_id: str) -> list[dict[str, Any]]:
        if self._history[session_id]:
            return list(self._history[session_id])
        if self._event_store is None:
            return []
        events = self._event_store.list_events(session_id, limit=MAX_EVENT_HISTORY)
        if not events:
            return []
        self._history[session_id].extend(events)
        self._sequences[session_id] = max(int(event["sequence"]) for event in events)
        return list(events)


event_broker = SessionEventBroker()
