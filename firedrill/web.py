"""Public Fire Drill web service: the static site plus a small live API.

Live mode runs the drill with server-side Grok calls (``XAI_API_KEY``).
Offline mode runs the same drill with templates and is labelled as such.
Simulated reviewers stay simulated: this is not a Switch room.

Safety:
- Starting a run needs ``FIREDRILL_ADMIN_TOKEN`` (Bearer). Unset = runs disabled.
- One run at a time, a cooldown, and a daily cap bound provider spend.
- Each run gets its own directory; the answer key stays there and is never served.
  Only aggregate metrics pass ``assert_public`` before they are stored or returned.
- The provider key is never returned, logged, or sent to the browser.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from firedrill.llm import LLM, LLMError
from firedrill.paths import DrillPaths, repo_root
from firedrill.public_metrics import assert_public, parse_report
from firedrill.simulate import run_demo

log = logging.getLogger("firedrill.web")
RUN_ID = re.compile(r"^run-[0-9a-f]{12}$")
MAX_BODY = 1024


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["live", "offline"] = "live"


DrillFn = Callable[[DrillPaths, bool, LLM], None]


def _default_drill(paths: DrillPaths, offline: bool, llm: LLM) -> None:
    run_demo(paths, offline=offline, llm=llm)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunManager:
    def __init__(self, data_dir: Path, drill: DrillFn = _default_drill) -> None:
        self.data_dir = data_dir
        self.runs_dir = data_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.drill = drill
        self.lock = threading.Lock()
        self.active: str | None = None
        self.started: deque[float] = deque()
        self.last_start = 0.0
        self.cooldown = _int("FIREDRILL_RUN_COOLDOWN_SECONDS", 60)
        self.daily_cap = _int("FIREDRILL_MAX_RUNS_PER_DAY", 10)
        self.keep = _int("FIREDRILL_KEEP_RUNS", 20)

    # storage -------------------------------------------------------------
    def _summary_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def save(self, run: dict[str, object]) -> None:
        text = assert_public(json.dumps(run, ensure_ascii=False, indent=2))
        tmp = self._summary_path(str(run["id"])).with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._summary_path(str(run["id"])))

    def get(self, run_id: str) -> dict[str, object] | None:
        if not RUN_ID.match(run_id):
            return None
        path = self._summary_path(run_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def list(self) -> list[dict[str, object]]:
        runs = []
        for path in sorted(self.runs_dir.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            run = json.loads(path.read_text(encoding="utf-8"))
            run.pop("metrics", None)
            runs.append(run)
        return runs

    def latest_metrics(self) -> dict[str, object] | None:
        for path in sorted(self.runs_dir.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            run = json.loads(path.read_text(encoding="utf-8"))
            if run.get("status") == "succeeded":
                return run.get("metrics")  # type: ignore[return-value]
        return None

    def _prune(self) -> None:
        files = sorted(self.runs_dir.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[self.keep :]:
            old.unlink(missing_ok=True)

    # lifecycle -----------------------------------------------------------
    def start(self, mode: str) -> dict[str, object]:
        offline = mode == "offline"
        llm = LLM(offline=offline)
        if not offline and llm.offline:
            raise HTTPException(503, "live mode needs XAI_API_KEY on the server; use mode=offline")
        now = time.time()
        with self.lock:
            if self.active:
                raise HTTPException(409, f"run {self.active} is already in progress")
            while self.started and now - self.started[0] > 86400:
                self.started.popleft()
            if len(self.started) >= self.daily_cap:
                raise HTTPException(429, "daily run cap reached")
            wait = self.cooldown - (now - self.last_start)
            if wait > 0:
                raise HTTPException(429, f"cooldown: retry in {int(wait) + 1}s")
            run_id = f"run-{secrets.token_hex(6)}"
            self.active = run_id
            self.started.append(now)
            self.last_start = now
        run: dict[str, object] = {
            "id": run_id,
            "mode": "live-llm" if not offline else "offline-template",
            "provider": None if offline else "xai",
            "model": None if offline else llm.model,
            "status": "running",
            "created_at": _now(),
            "finished_at": None,
            "llm_calls": 0,
            "error": None,
            "switch_room": False,
            "reviewers": "simulated",
        }
        self.save(run)
        threading.Thread(target=self._execute, args=(run, offline, llm), daemon=True).start()
        return run

    def _execute(self, run: dict[str, object], offline: bool, llm: LLM) -> None:
        workdir = self.data_dir / "work" / str(run["id"])
        try:
            paths = DrillPaths(root=workdir)
            paths.ensure()
            self.drill(paths, offline, llm)
            metrics = parse_report(paths.report.read_text(encoding="utf-8"))
            metrics["source"] = run["mode"]
            metrics["drill"] = {
                "id": run["id"],
                "title": "Live LLM drill (simulated reviewers)" if not offline else "Offline template drill",
                "recorded": False,
            }
            metrics["run"] = {k: run[k] for k in ("id", "mode", "provider", "model", "created_at")}
            assert_public(json.dumps(metrics))
            run.update(status="succeeded", metrics=metrics)
        except LLMError as exc:
            run.update(status="failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - surface a safe class name only
            log.error("run %s failed: %s", run["id"], exc.__class__.__name__)
            run.update(status="failed", error=f"drill failed ({exc.__class__.__name__})")
        finally:
            run["llm_calls"] = llm.calls
            run["finished_at"] = _now()
            shutil.rmtree(workdir, ignore_errors=True)  # answer key never outlives the run
            self.save(run)
            self._prune()
            with self.lock:
                self.active = None


class AuthThrottle:
    def __init__(self, limit: int = 10, window: float = 300.0) -> None:
        self.limit, self.window = limit, window
        self.fails: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def check(self, ip: str) -> None:
        now = time.time()
        with self.lock:
            q = self.fails.setdefault(ip, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(429, "too many failed attempts")

    def fail(self, ip: str) -> None:
        with self.lock:
            self.fails.setdefault(ip, deque()).append(time.time())


def create_app(data_dir: Path | None = None, drill: DrillFn = _default_drill, static_dir: Path | None = None) -> FastAPI:
    data = Path(data_dir or os.environ.get("FIREDRILL_DATA_DIR") or "/tmp/firedrill-live")
    manager = RunManager(data, drill)
    throttle = AuthThrottle()
    app = FastAPI(title="Fire Drill", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager

    @app.middleware("http")
    async def guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY:
            return JSONResponse({"detail": "body too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_admin(request: Request, authorization: str | None) -> None:
        ip = request.client.host if request.client else "?"
        throttle.check(ip)
        expected = os.environ.get("FIREDRILL_ADMIN_TOKEN", "").strip()
        if not expected:
            raise HTTPException(403, "runs are disabled: FIREDRILL_ADMIN_TOKEN is not set")
        given = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(given.encode(), expected.encode()):
            throttle.fail(ip)
            raise HTTPException(401, "unauthorized")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        llm = LLM()
        return {
            "ok": True,
            "live_llm_available": not llm.offline,
            "provider": "xai",
            "model": llm.model,
            "runs_enabled": bool(os.environ.get("FIREDRILL_ADMIN_TOKEN", "").strip()),
            "active_run": manager.active,
            "switch_connected": False,
            "reviewers": "simulated",
        }

    @app.get("/api/metrics/latest")
    def latest() -> dict[str, object]:
        metrics = manager.latest_metrics()
        if metrics is None:
            raise HTTPException(404, "no completed run yet; the dashboard shows the recorded drill")
        return metrics

    @app.get("/api/runs")
    def runs() -> dict[str, object]:
        return {"runs": manager.list()}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> dict[str, object]:
        found = manager.get(run_id)
        if found is None:
            raise HTTPException(404, "run not found")
        return found

    @app.post("/api/runs", status_code=202)
    def start(body: RunIn, request: Request, authorization: str | None = Header(default=None)) -> dict[str, object]:
        require_admin(request, authorization)
        return manager.start(body.mode)

    static = static_dir or repo_root() / "public"
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="site")
    return app


def app_from_env() -> FastAPI:
    return create_app()
