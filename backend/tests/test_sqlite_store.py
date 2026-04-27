import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.sessions import SessionInfo
from app.storage.screenshot_store import ScreenshotMetadata
from app.storage.sqlite import SQLiteStore


class SQLiteStoreTests(unittest.TestCase):
    def test_records_sessions_messages_events_and_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(str(Path(tmp) / "agent.sqlite"))
            store.initialize()

            session = SessionInfo(
                session_id="abc123",
                status="running",
                container_id="container",
                vnc_url="/vnc/sessions/abc123/",
            )
            store.record_session(session, now=10.0)
            store.record_message(session_id="abc123", role="user", text="hello", ts=11.0)
            store.record_event(
                {
                    "type": "agent_message",
                    "session_id": "abc123",
                    "ts": 12.0,
                    "sequence": 1,
                    "text": "done",
                }
            )
            store.record_screenshot(
                ScreenshotMetadata(
                    shot_id="f" * 32,
                    session_id="abc123",
                    path=Path(tmp) / "shot.png",
                    thumb_path=Path(tmp) / "shot.webp",
                    sha256="0" * 64,
                    size_bytes=123,
                    ts=13.0,
                )
            )

            sessions = store.list_sessions()
            events = store.list_events("abc123")

            self.assertEqual(sessions[0]["session_id"], "abc123")
            self.assertEqual(events[0]["type"], "agent_message")
            self.assertEqual(events[0]["text"], "done")

    def test_rejects_base64_event_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(str(Path(tmp) / "agent.sqlite"))
            store.initialize()

            with self.assertRaises(ValueError):
                store.record_event(
                    {
                        "type": "screenshot",
                        "session_id": "abc123",
                        "ts": time.time(),
                        "sequence": 1,
                        "url": "/x.png",
                        "thumb_url": "/x.webp",
                        "sha256": "0" * 64,
                        "base64": "not allowed",
                    }
                )

    def test_deletes_expired_screenshot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(str(Path(tmp) / "agent.sqlite"))
            store.initialize()
            old_png = Path(tmp) / "old.png"
            old_thumb = Path(tmp) / "old.webp"

            store.record_screenshot(
                ScreenshotMetadata(
                    shot_id="a" * 32,
                    session_id="abc123",
                    path=old_png,
                    thumb_path=old_thumb,
                    sha256="1" * 64,
                    size_bytes=12,
                    ts=1.0,
                )
            )

            paths = store.delete_screenshots_older_than(2.0)

            self.assertEqual(paths, [old_png, old_thumb])

    def test_clear_session_history_removes_stale_messages_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(str(Path(tmp) / "agent.sqlite"))
            store.initialize()
            store.record_message(session_id="abc123", role="user", text="old", ts=1.0)
            store.record_event(
                {
                    "type": "agent_message",
                    "session_id": "abc123",
                    "ts": 2.0,
                    "sequence": 1,
                    "text": "old",
                }
            )

            store.clear_session_history("abc123")

            self.assertEqual(store.list_events("abc123"), [])


if __name__ == "__main__":
    unittest.main()
