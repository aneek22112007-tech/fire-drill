"""Apply the worker's structured edits and render a unified diff.

This module never runs a shell. Canary text is not applied here.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path

from firedrill.models import Action


def read_version(repo: Path) -> str:
    return (repo / "VERSION").read_text(encoding="utf-8").strip()


def bump_patch(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def parse_flat_config(text: str) -> dict[str, str | int | bool]:
    data: dict[str, str | int | bool] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        data[key.strip()] = _coerce(raw.strip())
    return data


def dump_flat_config(data: dict[str, str | int | bool]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    return "\n".join(lines) + "\n"


