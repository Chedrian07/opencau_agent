import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.events import SessionEventBroker
from app.schemas.events import AgentEvent
from app.storage.sqlite import SQLiteStore


class AgentEventSchemaTests(unittest.TestCase):
    def test_accepts_screenshot_metadata_without_image_payload(self) -> None:
        adapter = TypeAdapter(AgentEvent)

        event = adapter.validate_python(
            {
                "type": "screenshot",
                "session_id": "abc123",
                "ts": 1.0,
                "sequence": 1,
                "url": "/api/sessions/abc123/screenshots/shot.png",
                "thumb_url": "/api/sessions/abc123/screenshots/shot.png",
                "sha256": "0" * 64,
            }
        )

        self.assertEqual(event.type, "screenshot")

    def test_rejects_screenshot_base64_extra_payload(self) -> None:
        adapter = TypeAdapter(AgentEvent)

        with self.assertRaises(ValidationError):
            adapter.validate_python(
                {
                    "type": "screenshot",
                    "session_id": "abc123",
                    "ts": 1.0,
                    "sequence": 1,
                    "url": "/api/sessions/abc123/screenshots/shot.png",
                    "thumb_url": "/api/sessions/abc123/screenshots/shot.png",
                    "sha256": "0" * 64,
                    "base64": "not allowed",
                }
            )


class SessionEventBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_replays_history_to_late_subscriber(self) -> None:
        broker = SessionEventBroker()
        await broker.publish("abc123", "agent_message", text="hello")

        subscription = broker.subscribe("abc123")
        event = await asyncio.wait_for(anext(subscription), timeout=1)
        await subscription.aclose()

        self.assertEqual(event["type"], "agent_message")
        self.assertEqual(event["sequence"], 1)

    async def test_clear_removes_history_and_resets_sequence(self) -> None:
        broker = SessionEventBroker()
        await broker.publish("abc123", "agent_message", text="hello")
        await broker.clear("abc123")
        event = await broker.publish("abc123", "agent_message", text="again")

        self.assertEqual(event["sequence"], 1)
        self.assertEqual(await broker.history("abc123"), [event])

    async def test_history_falls_back_to_sqlite_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(str(Path(tmp) / "agent.sqlite"))
            store.initialize()
            broker = SessionEventBroker()
            broker.configure_persistence(store)
            await broker.publish("abc123", "agent_message", text="hello")

            fresh_broker = SessionEventBroker()
            fresh_broker.configure_persistence(store)
            history = await fresh_broker.history("abc123")

        self.assertEqual(history[0]["type"], "agent_message")
        self.assertEqual(history[0]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
