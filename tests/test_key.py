"""M4: worker and canary cannot read the key, and the commitment matches the reveal."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from firedrill.cli import app
from firedrill.commitment import commitment_hash, commitment_message, reveal_message, verify_reveal_text
from firedrill.paths import DrillPaths
from firedrill.service import create_app, running_auditor, uvicorn_command
from firedrill.simulate import build_events, play
from firedrill.store import AuditorStore

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()

_PROBE = """
import os
import sys
import httpx

base, path, method = sys.argv[1], sys.argv[2], sys.argv[3]
token = os.environ.get("PROBE_TOKEN", "")
headers = {"Authorization": "Bearer " + token} if token else {}
body = None
if method == "POST":
    body = {"request_id": "fd-aabbccdd", "flaw_id": "fake-secret"}
response = httpx.request(method, base + path, headers=headers, json=body, timeout=5)
print(response.status_code)
"""


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


def _http_status(base: str, path: str, method: str, token: str) -> str:
    env = os.environ.copy()
    if token:
        env["PROBE_TOKEN"] = token
    else:
        env.pop("PROBE_TOKEN", None)
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE, base, path, method],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    if token:
        assert token not in completed.stdout
    return completed.stdout.strip()


def test_worker_and_canary_processes_receive_401(tmp_path):
    _write_private(tmp_path)
    paths = DrillPaths(root=tmp_path)
    with running_auditor(paths) as base:
        assert _http_status(base, "/key", "GET", "") == "401"
        assert _http_status(base, "/key", "GET", "ingest-token") == "401"
        assert _http_status(base, "/mappings", "POST", "ingest-token") == "201"
        assert _http_status(base, "/mappings/fd-aabbccdd", "GET", "ingest-token") == "401"
        assert _http_status(base, "/key", "GET", "auditor-token") == "200"


def test_play_writes_mappings_only_through_the_service(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_SECRET", "test-worker-secret")
    calls: list[str] = []
    real = AuditorStore.add_mapping

    def spy(self, request_id: str, flaw_id: str) -> None:  # type: ignore[no-untyped-def]
        calls.append(request_id)
        real(self, request_id, flaw_id)

    monkeypatch.setattr(AuditorStore, "add_mapping", spy)
    paths = DrillPaths(root=tmp_path)
    events = build_events(DrillPaths(root=ROOT), offline=True)
    play(paths, events)
    assert calls == []
    store = AuditorStore(paths.drill_db)
    try:
        assert len(store.mappings()) == 12
    finally:
        store.close()


def test_serve_command_binds_loopback_and_refuses_without_setup(tmp_path, monkeypatch):
    command = uvicorn_command(8765)
    assert "127.0.0.1" in command
    assert "0.0.0.0" not in command
    monkeypatch.setenv("FIREDRILL_ROOT", str(tmp_path))
    refused = runner.invoke(app, ["serve"])
    assert refused.exit_code != 0
    assert "missing" in refused.output
    assert "setup" in refused.output


def test_setup_user_command_matches_the_os():
    path = ROOT / "scripts" / "setup_auditor.py"
    spec = importlib.util.spec_from_file_location("setup_auditor", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.creation_argv("Linux") == ["sudo", "-n", "useradd", "--system", "firedrill-auditor"]
    darwin = module.creation_argv("Darwin")
    assert darwin is not None and "sysadminctl" in darwin
    assert module.creation_argv("FreeBSD") is None
    assert "useradd" in module.user_setup_warning("Linux")
    assert "token-only" in module.user_setup_warning("Linux")
    assert "sysadminctl" in module.user_setup_warning("Darwin")
    assert "token-only" in module.user_setup_warning("Darwin")
    assert "token-only" in module.user_setup_warning("FreeBSD")


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
