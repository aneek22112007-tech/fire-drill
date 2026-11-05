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


def main() -> int:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    current = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else example
    values = _parse(current)
    tokens = json.loads(TOKENS.read_text(encoding="utf-8")) if TOKENS.exists() else {}
    if not values.get("WORKER_SECRET"):
        values["WORKER_SECRET"] = secrets.token_hex(32)
    if not values.get("AUDITOR_TOKEN") and tokens.get("auditor_token"):
        values["AUDITOR_TOKEN"] = tokens["auditor_token"]
    if not values.get("CANARY_INGEST_TOKEN") and tokens.get("canary_ingest_token"):
        values["CANARY_INGEST_TOKEN"] = tokens["canary_ingest_token"]
    lines: list[str] = []
    seen: set[str] = set()
    for line in current.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key = line.split("=", 1)[0]
        seen.add(key)
        if key in values:
            lines.append(f"{key}={values[key]}")
        else:
            lines.append(line)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV_PATH.chmod(0o600)
    print("wrote .env (secrets not shown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
