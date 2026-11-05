"""In-process room: SQLite message log with commit order, threads, and private channels."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from firedrill.models import RoomMessage


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LocalAdapter:
    """SQLite-backed room.

    `seq` is the commit order, matching Switch's per-room log. Timestamps are
    stored and returned, but they do not reorder messages.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT UNIQUE NOT NULL,
                ts TEXT NOT NULL,
                author TEXT NOT NULL,
                role TEXT NOT NULL,
                thread_id TEXT,
                body TEXT NOT NULL,
                channel TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                user TEXT NOT NULL,
                emoji TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

