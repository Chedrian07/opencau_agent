import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.schemas.sessions import SessionInfo
from app.storage.session_store import RedisSessionManager


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_profile="mock",
        redis_url="redis://unused:6379/0",
        sandbox_idle_timeout_sec=60,
    )


class RedisSessionManagerMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_backend_tracks_active_and_expired_sessions(self) -> None:
        manager = RedisSessionManager(_settings(), force_memory=True)
        await manager.connect()

        await manager.upsert_session(
            SessionInfo(
                session_id="abc123",
                status="running",
                container_id="container",
                vnc_url="/vnc/sessions/abc123/",
            ),
            now=10.0,
        )
        await manager.touch("abc123", now=20.0)

        self.assertEqual(manager.backend_name, "memory")
        self.assertEqual(await manager.active_session_ids(), {"abc123"})
        self.assertEqual(await manager.expired_session_ids(now=79.0), [])
        self.assertEqual(await manager.expired_session_ids(now=81.0), ["abc123"])

    async def test_mark_deleted_hides_session_from_active_listing(self) -> None:
        manager = RedisSessionManager(_settings(), force_memory=True)
        await manager.upsert_session(
            SessionInfo(session_id="abc123", status="running", container_id=None, vnc_url=None),
            now=10.0,
        )

        await manager.mark_deleted("abc123", now=11.0)

        self.assertEqual(await manager.list_sessions(), [])
        all_sessions = await manager.list_sessions(include_deleted=True)
        self.assertEqual(all_sessions[0].session_id, "abc123")
        self.assertIsNotNone(all_sessions[0].deleted_at)


if __name__ == "__main__":
    unittest.main()
