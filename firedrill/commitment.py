"""Answer-key commitment. SHA-256(key.json bytes + newline + salt)."""

from __future__ import annotations

import base64
import hashlib
import re


def commitment_hash(key_bytes: bytes, salt: str) -> str:
    return hashlib.sha256(key_bytes + b"\n" + salt.encode("utf-8")).hexdigest()


def commitment_message(digest: str) -> str:
    return f"COMMITMENT sha256={digest}"


def reveal_message(key_bytes: bytes, salt: str) -> str:
    digest = commitment_hash(key_bytes, salt)
    encoded = base64.b64encode(key_bytes).decode("ascii")
    return f"REVEAL sha256={digest}\nSALT {salt}\nKEY_B64 {encoded}"


_REVEAL = re.compile(
    r"REVEAL sha256=([0-9a-f]{64})\nSALT ([^\n]+)\nKEY_B64 ([A-Za-z0-9+/=\n]+)",
    re.S,
)


