"""Token-gated auditor service. Only the auditor token can read the answer key."""

from __future__ import annotations

import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from firedrill.paths import DrillPaths, default_paths, repo_root
from firedrill.report import render_dashboard
from firedrill.store import AuditorStore, load_tokens

BIND_HOST = "127.0.0.1"

_BEARER = "Bearer "


class MappingIn(BaseModel):
    request_id: str
    flaw_id: str


def create_app(key_file: Path, tokens_file: Path, drill_db: Path) -> FastAPI:
    key_path = Path(key_file)
    tokens = load_tokens(tokens_file)
    store = AuditorStore(drill_db)
    app = FastAPI(title="Fire Drill auditor", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.key_path = key_path
    app.state.tokens = tokens

    def presented(authorization: str | None) -> str:
        if not authorization or not authorization.startswith(_BEARER):
            return ""
        return authorization[len(_BEARER) :].strip()

    def require_auditor(authorization: str | None) -> None:
        if presented(authorization) != tokens["auditor_token"]:
            raise HTTPException(status_code=401, detail="unauthorized")

    def require_ingest(authorization: str | None) -> None:
        token = presented(authorization)
        allowed = {tokens["auditor_token"], tokens["canary_ingest_token"]}
        if token not in allowed:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mappings", status_code=201)
    def add_mapping(body: MappingIn, authorization: str | None = Header(default=None)) -> dict[str, str]:
        require_ingest(authorization)
        store.add_mapping(body.request_id, body.flaw_id)
        return {"status": "stored"}

    @app.get("/mappings/{request_id}")
    def get_mapping(request_id: str, authorization: str | None = Header(default=None)) -> dict[str, str]:
        require_auditor(authorization)
        flaw_id = store.mapping_for(request_id)
        if flaw_id is None:
            raise HTTPException(status_code=404, detail="unknown request")
        return {"request_id": request_id, "flaw_id": flaw_id}

    @app.get("/key")
    def read_key(authorization: str | None = Header(default=None)) -> dict[str, object]:
        require_auditor(authorization)
        raw = key_path.read_bytes()
        return {"key": json.loads(raw.decode("utf-8")), "bytes": raw.decode("utf-8")}

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(authorization: str | None = Header(default=None)) -> str:
        require_auditor(authorization)
        return render_dashboard(store)

    return app


def app_from_env() -> FastAPI:
    """Uvicorn factory. FIREDRILL_ROOT selects the auditor_private directory."""

    paths = default_paths()
    return create_app(paths.key_file, paths.tokens_file, paths.drill_db)


def ensure_tokens(path: Path) -> None:
    """Write ingest and auditor tokens if setup has not already. Mode 0600."""

    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)
        return
    payload = {
        "auditor_token": secrets.token_hex(32),
        "canary_ingest_token": secrets.token_hex(32),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def uvicorn_command(port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "firedrill.service:app_from_env",
        "--factory",
        "--host",
        BIND_HOST,
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((BIND_HOST, 0))
        return int(sock.getsockname()[1])


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=5)


def _wait_until_ready(base: str, proc: subprocess.Popen[bytes], log_path: Path) -> None:
    deadline = time.monotonic() + 15
    last_error = "no response"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            response = httpx.get(base + "/health", timeout=0.5)
        except httpx.HTTPError as exc:
            last_error = exc.__class__.__name__
            time.sleep(0.05)
            continue
        if response.status_code == 200:
            return
        last_error = f"HTTP {response.status_code}"
        time.sleep(0.05)
    _stop(proc)
    detail = ""
    if log_path.is_file():
        detail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
    raise RuntimeError(
        f"auditor service on {BIND_HOST} did not become ready ({last_error}). {detail}".rstrip()
    )


@contextmanager
def running_auditor(paths: DrillPaths) -> Iterator[str]:
    """Start the auditor service as a subprocess and stop it on the way out."""

    paths.ensure()
    ensure_tokens(paths.tokens_file)
    port = _free_port()
    log_path = paths.data / "auditor-service.log"
    log_handle = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["FIREDRILL_ROOT"] = str(paths.root)
    env["PYTHONPATH"] = str(repo_root()) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        uvicorn_command(port),
        cwd=repo_root(),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    base = f"http://{BIND_HOST}:{port}"
    try:
        _wait_until_ready(base, proc, log_path)
        yield base
    finally:
        _stop(proc)
        log_handle.close()
