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

