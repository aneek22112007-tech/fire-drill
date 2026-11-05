#!/usr/bin/env python3
"""Create auditor_private and, when the OS allows it, the firedrill-auditor user.

Creating a macOS user needs an administrator password. This script tries a
non-interactive sudo. When that is refused it keeps going: the directory is
mode 0700 and the token-gated service is the isolation boundary.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITOR_DIR = ROOT / "auditor_private"
USER_NAME = "firedrill-auditor"


def _try_create_user() -> str:
    probe = subprocess.run(
        ["id", USER_NAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return "present"
    created = subprocess.run(
        ["sudo", "-n", "sysadminctl", "-addUser", USER_NAME, "-shell", "/usr/bin/false"],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode == 0:
        return "created"
    return "unavailable"


def _write_key(path: Path) -> None:
    if path.exists():
        return
    payload = {
        "version": 1,
        "drill_key": secrets.token_hex(32),
        "purpose": "fire-drill answer-key seal",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _write_tokens(path: Path) -> None:
    if path.exists():
        return
    payload = {
        "auditor_token": secrets.token_hex(32),
        "canary_ingest_token": secrets.token_hex(32),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> int:
    AUDITOR_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(AUDITOR_DIR, 0o700)
    user_state = _try_create_user()
    if user_state == "created":
        subprocess.run(
            ["sudo", "-n", "chown", "-R", f"{USER_NAME}:staff", str(AUDITOR_DIR)],
            check=False,
        )
    _write_key(AUDITOR_DIR / "key.json")
    _write_tokens(AUDITOR_DIR / "tokens.json")
    note = AUDITOR_DIR / "README.txt"
    note.write_text(
        "Answer-key directory for Fire Drill.\n"
        f"OS user firedrill-auditor: {user_state}.\n"
        "When the user is unavailable, isolation is the token-gated service on 127.0.0.1.\n"
        "The canary ingest token cannot read key.json. Do not commit this directory.\n",
        encoding="utf-8",
    )
    os.chmod(note, 0o600)
    mode = stat.S_IMODE(AUDITOR_DIR.stat().st_mode)
    print(f"auditor_private mode {mode:o}; firedrill-auditor: {user_state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
