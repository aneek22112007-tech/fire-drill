"""Worker-signed registry. The executor trusts an id only when the HMAC matches."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from pathlib import Path

from firedrill.models import Action


class RegistryError(RuntimeError):
    pass


def load_worker_secret() -> bytes:
    secret = os.environ.get("WORKER_SECRET", "")
    if not secret:
        raise RegistryError("WORKER_SECRET is not set")
    return secret.encode("utf-8")


def sign_request(secret: bytes, request_id: str) -> str:
    return hmac.new(secret, request_id.encode("utf-8"), hashlib.sha256).hexdigest()


class WorkerRegistry:
    def __init__(self, db_path: Path, secret: bytes) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._secret = secret
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registry (
                request_id TEXT PRIMARY KEY,
                signature TEXT NOT NULL,
                action_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def register(self, request_id: str, action: Action) -> str:
        signature = sign_request(self._secret, request_id)
        payload = action.model_dump_json()
        with self._lock:
            self._conn.execute(
                "INSERT INTO registry (request_id, signature, action_json) VALUES (?, ?, ?)",
                (request_id, signature, payload),
            )
            self._conn.commit()
        return signature

    def contains(self, request_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM registry WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return row is not None

    def get(self, request_id: str) -> tuple[str, Action] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT signature, action_json FROM registry WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        action = Action.model_validate(json.loads(row["action_json"]))
        return row["signature"], action

    def verify(self, request_id: str) -> Action:
        found = self.get(request_id)
        if found is None:
            raise RegistryError(f"refused {request_id}: not in the worker registry")
        signature, action = found
        expected = sign_request(self._secret, request_id)
        if not hmac.compare_digest(signature, expected):
            raise RegistryError(f"refused {request_id}: signature does not match")
        return action
