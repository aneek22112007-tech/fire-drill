#!/usr/bin/env python3
"""Fill empty secrets in .env from auditor_private/tokens.json. Never prints them."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
TOKENS = ROOT / "auditor_private" / "tokens.json"


def _parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


