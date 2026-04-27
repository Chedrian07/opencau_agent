from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.schemas.sessions import SessionInfo
from app.storage.screenshot_store import ScreenshotMetadata


BASE_EVENT_KEYS = {"type", "session_id", "ts", "sequence"}


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _ensure_safe_payload(value: Any) -> None:
    if isinstance(value, dict):
        if "base64" in value:
            raise ValueError("event payload must not contain base64 data")
        for child in value.values():
            _ensure_safe_payload(child)
        return
    if isinstance(value, list):
        for child in value:
            _ensure_safe_payload(child)
        return
    if isinstance(value, str) and value.startswith("data:image/"):
        raise ValueError("event payload must not contain data URLs")


class SQLiteStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self._path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    container_id TEXT,
                    vnc_url TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_active_at REAL NOT NULL,
                    deleted_at REAL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ts REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_ts
                    ON messages(session_id, ts);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    ts REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(session_id, sequence)
                );

                CREATE INDEX IF NOT EXISTS idx_events_session_sequence
                    ON events(session_id, sequence);

                CREATE TABLE IF NOT EXISTS screenshots (
                    shot_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    thumb_path TEXT,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    ts REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_screenshots_session_ts
                    ON screenshots(session_id, ts);
                """
            )

    def record_session(self, session: SessionInfo, *, now: float | None = None) -> None:
        ts = now or time.time()
        with _connect(self._path) as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, status, container_id, vnc_url, created_at,
                    updated_at, last_active_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(session_id) DO UPDATE SET
                    status=excluded.status,
                    container_id=excluded.container_id,
                    vnc_url=excluded.vnc_url,
                    updated_at=excluded.updated_at,
                    last_active_at=excluded.last_active_at,
                    deleted_at=NULL
                """,
                (
                    session.session_id,
                    session.status,
                    session.container_id,
                    session.vnc_url,
                    ts,
                    ts,
                    ts,
                ),
            )

    def touch_session(self, session_id: str, *, now: float | None = None) -> None:
        ts = now or time.time()
        with _connect(self._path) as connection:
            connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?, last_active_at = ?
                WHERE session_id = ? AND deleted_at IS NULL
                """,
                (ts, ts, session_id),
            )

    def mark_session_deleted(self, session_id: str, *, now: float | None = None) -> None:
        ts = now or time.time()
        with _connect(self._path) as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = 'missing', updated_at = ?, deleted_at = ?
                WHERE session_id = ?
                """,
                (ts, ts, session_id),
            )

    def list_sessions(self, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with _connect(self._path) as connection:
            rows = connection.execute(
                f"""
                SELECT session_id, status, container_id, vnc_url, created_at,
                       updated_at, last_active_at, deleted_at
                FROM sessions
                {where}
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def record_message(
        self,
        *,
        session_id: str,
        role: str,
        text: str,
        ts: float | None = None,
    ) -> None:
        timestamp = ts or time.time()
        with _connect(self._path) as connection:
            connection.execute(
                """
                INSERT INTO messages(session_id, role, text, ts)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, text, timestamp),
            )

    def record_event(self, event: dict[str, Any]) -> None:
        _ensure_safe_payload(event)
        payload_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
        with _connect(self._path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO events(session_id, sequence, type, ts, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event["session_id"],
                    event["sequence"],
                    event["type"],
                    event["ts"],
                    payload_json,
                ),
            )

    def list_events(self, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with _connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM events
                WHERE session_id = ?
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        events = [json.loads(row["payload_json"]) for row in reversed(rows)]
        return [event for event in events if BASE_EVENT_KEYS <= set(event)]

    def clear_session_history(self, session_id: str) -> None:
        with _connect(self._path) as connection:
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM events WHERE session_id = ?", (session_id,))

    def record_screenshot(self, metadata: ScreenshotMetadata) -> None:
        with _connect(self._path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO screenshots(
                    shot_id, session_id, path, thumb_path, sha256, size_bytes, ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.shot_id,
                    metadata.session_id,
                    str(metadata.path),
                    str(metadata.thumb_path) if metadata.thumb_path else None,
                    metadata.sha256,
                    metadata.size_bytes,
                    metadata.ts,
                ),
            )

    def delete_screenshots_older_than(self, cutoff_ts: float) -> list[Path]:
        with _connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT path, thumb_path
                FROM screenshots
                WHERE ts < ?
                """,
                (cutoff_ts,),
            ).fetchall()
            connection.execute("DELETE FROM screenshots WHERE ts < ?", (cutoff_ts,))

        paths: list[Path] = []
        for row in rows:
            paths.append(Path(row["path"]))
            if row["thumb_path"]:
                paths.append(Path(row["thumb_path"]))
        return paths
