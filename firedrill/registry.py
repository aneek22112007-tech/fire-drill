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


