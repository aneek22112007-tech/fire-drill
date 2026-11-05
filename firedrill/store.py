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

    def add_mapping(self, request_id: str, flaw_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO mappings (request_id, flaw_id) VALUES (?, ?)",
                (request_id, flaw_id),
            )
            self._conn.execute(
                "UPDATE requests SET is_canary = 1, flaw_id = ? WHERE id = ?",
                (flaw_id, request_id),
            )
            self._conn.commit()

    def mapping_for(self, request_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT flaw_id FROM mappings WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return None if row is None else str(row["flaw_id"])

    def mappings(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT request_id, flaw_id FROM mappings").fetchall()
        return {row["request_id"]: row["flaw_id"] for row in rows}

    def upsert_request(
        self,
        *,
        request_id: str,
        summary: str,
        diff: str,
        risk: str,
        complexity: int,
        created_ts: str,
        flaw_id: str | None = None,
        mast_mode: str | None = None,
        assigned_reviewer: str | None = None,
    ) -> None:
        is_canary = 1 if flaw_id else 0
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO requests (
                    id, summary, diff, risk, complexity, created_ts,
                    is_canary, flaw_id, mast_mode, assigned_reviewer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    summary = excluded.summary,
                    diff = excluded.diff,
                    risk = excluded.risk,
                    complexity = excluded.complexity,
                    created_ts = excluded.created_ts,
                    is_canary = MAX(requests.is_canary, excluded.is_canary),
                    flaw_id = COALESCE(excluded.flaw_id, requests.flaw_id),
                    mast_mode = COALESCE(excluded.mast_mode, requests.mast_mode),
                    assigned_reviewer = COALESCE(excluded.assigned_reviewer, requests.assigned_reviewer)
                """,
                (
                    request_id,
                    summary,
                    diff,
                    risk,
                    complexity,
                    created_ts,
                    is_canary,
                    flaw_id,
                    mast_mode,
                    assigned_reviewer,
                ),
            )
            self._conn.commit()

    def set_mast(self, request_id: str, mast_mode: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE requests SET mast_mode = ? WHERE id = ?",
                (mast_mode, request_id),
            )
            self._conn.commit()

