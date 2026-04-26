from collections import defaultdict, deque
from collections.abc import AsyncIterator
import asyncio
import time
from typing import Any

from pydantic import TypeAdapter

from app.schemas.events import AgentEvent

MAX_EVENT_HISTORY = 200
EVENT_ADAPTER = TypeAdapter(AgentEvent)


class SessionEventBroker:
    def __init__(self) -> None:
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=MAX_EVENT_HISTORY))
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

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

        for queue in subscribers:
            queue.put_nowait(event)
        return event

    async def subscribe(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            replay = list(self._history[session_id])
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
            return list(self._history[session_id])

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._history.pop(session_id, None)
            self._sequences.pop(session_id, None)


event_broker = SessionEventBroker()
