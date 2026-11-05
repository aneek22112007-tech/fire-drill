"""Answer-key commitment. SHA-256(key.json bytes + newline + salt)."""

from __future__ import annotations

import base64
import hashlib
import re


def commitment_hash(key_bytes: bytes, salt: str) -> str:
    return hashlib.sha256(key_bytes + b"\n" + salt.encode("utf-8")).hexdigest()


def commitment_message(digest: str) -> str:
    return f"COMMITMENT sha256={digest}"


