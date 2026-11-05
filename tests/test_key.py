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


def test_worker_and_canary_cannot_read_the_key(tmp_path):
    key_file, tokens_file, drill_db, key_bytes = _write_private(tmp_path)
    client = TestClient(create_app(key_file, tokens_file, drill_db))

    worker = client.get("/key")
    assert worker.status_code == 401

    canary = client.get("/key", headers={"Authorization": "Bearer ingest-token"})
    assert canary.status_code == 401

    posted = client.post(
        "/mappings",
        headers={"Authorization": "Bearer ingest-token"},
        json={"request_id": "fd-aabbccdd", "flaw_id": "fake-secret"},
    )
    assert posted.status_code == 201
    listed = client.get(
        "/mappings/fd-aabbccdd",
        headers={"Authorization": "Bearer ingest-token"},
    )
    assert listed.status_code == 401

    auditor = client.get("/key", headers={"Authorization": "Bearer auditor-token"})
    assert auditor.status_code == 200
    assert auditor.json()["bytes"].encode("utf-8") == key_bytes


def test_commitment_matches_revealed_key(tmp_path):
    _key_file, _tokens, _db, key_bytes = _write_private(tmp_path)
    salt = "drill-salt-1"
    digest = commitment_hash(key_bytes, salt)
    opening = commitment_message(digest)
    reveal = reveal_message(key_bytes, salt)
    ok, actual = verify_reveal_text(opening + "\n" + reveal)
    assert ok
    assert actual == digest
    assert f"sha256={digest}" in opening
