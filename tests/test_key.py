"""M4: worker and canary cannot read the key, and the commitment matches the reveal."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from firedrill.commitment import commitment_hash, commitment_message, reveal_message, verify_reveal_text
from firedrill.service import create_app


def _write_private(tmp_path: Path) -> tuple[Path, Path, Path, bytes]:
    private = tmp_path / "auditor_private"
    private.mkdir()
    private.chmod(0o700)
    key = {"version": 1, "drill_key": "abc123", "purpose": "test"}
    key_bytes = (json.dumps(key, indent=2, sort_keys=True) + "\n").encode("utf-8")
    key_file = private / "key.json"
    key_file.write_bytes(key_bytes)
    key_file.chmod(0o600)
    tokens = {"auditor_token": "auditor-token", "canary_ingest_token": "ingest-token"}
    tokens_file = private / "tokens.json"
    tokens_file.write_text(json.dumps(tokens), encoding="utf-8")
    return key_file, tokens_file, private / "drill.db", key_bytes


