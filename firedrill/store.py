"""Private auditor database. The room never reads this file."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from firedrill.models import Decision


class AuditorStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mappings (
                request_id TEXT PRIMARY KEY,
                flaw_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                diff TEXT NOT NULL,
                risk TEXT NOT NULL,
                complexity INTEGER NOT NULL,
                created_ts TEXT NOT NULL,
                is_canary INTEGER NOT NULL DEFAULT 0,
                flaw_id TEXT,
                mast_mode TEXT,
                assigned_reviewer TEXT
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                latency_s REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS adaptations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                rule TEXT NOT NULL,
                reviewer TEXT,
                reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS consent (
                reviewer TEXT PRIMARY KEY,
                ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

