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

