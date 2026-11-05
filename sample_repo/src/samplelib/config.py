"""Read the flat config.yaml next to this repository."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _coerce(raw: str) -> str | int | bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.isdigit():
        return int(raw)
    return raw


def load(path: Path | None = None) -> dict[str, str | int | bool]:
    target = path or (repo_root() / "config.yaml")
    data: dict[str, str | int | bool] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        data[key.strip()] = _coerce(raw.strip())
    return data
