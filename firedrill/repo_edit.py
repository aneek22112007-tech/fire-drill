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


def _coerce(raw: str) -> str | int | bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.isdigit():
        return int(raw)
    return raw


def apply_action(repo: Path, action: Action) -> None:
    if action.kind == "version_bump":
        if not action.version:
            raise ValueError("version_bump requires version")
        (repo / "VERSION").write_text(action.version + "\n", encoding="utf-8")
        return
    if action.kind == "config_set":
        if not action.key or action.value is None:
            raise ValueError("config_set requires key and value")
        path = repo / "config.yaml"
        data = parse_flat_config(path.read_text(encoding="utf-8"))
        data[action.key] = action.value
        path.write_text(dump_flat_config(data), encoding="utf-8")
        return
    if action.kind == "add_function":
        if not action.function_name or not action.function_body or not action.test_body:
            raise ValueError("add_function requires function and test bodies")
        ops = repo / "src" / "samplelib" / "ops.py"
        existing = ops.read_text(encoding="utf-8")
        marker = f"def {action.function_name}("
        if marker not in existing:
            ops.write_text(existing.rstrip() + "\n\n" + action.function_body.rstrip() + "\n", encoding="utf-8")
        tests = repo / "tests" / "test_sample.py"
        test_text = tests.read_text(encoding="utf-8")
        test_marker = f"def {action.test_name}("
        if action.test_name and test_marker not in test_text:
            tests.write_text(test_text.rstrip() + "\n\n" + action.test_body.rstrip() + "\n", encoding="utf-8")
        return
    raise ValueError(f"unknown action {action.kind}")


def _snapshot(repo: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(repo.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        files[path.relative_to(repo).as_posix()] = path.read_text(encoding="utf-8")
    return files


