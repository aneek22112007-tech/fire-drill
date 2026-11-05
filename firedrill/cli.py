"""Fire Drill command line."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from firedrill import __version__
from firedrill.adapters.base import AdapterError
from firedrill.adapters.local import LocalAdapter
from firedrill.agents.auditor import Auditor
from firedrill.agents.canary import load_library
from firedrill.commitment import verify_reveal_text
from firedrill.envfile import load_env_file
from firedrill.executor import Executor
from firedrill.humans import REVIEWERS
from firedrill.paths import default_paths
from firedrill.registry import WorkerRegistry
from firedrill.report import write_report
from firedrill.session import ConsentError, DrillSession
from firedrill.simulate import replay as replay_recording
from firedrill.simulate import run_demo as play_demo
from firedrill.store import AuditorStore
from firedrill.timeutil import format_ts

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console(soft_wrap=True)


@app.callback()
def main() -> None:
    """Chaos engineering for human oversight of AI agents."""

    load_env_file(default_paths().root / ".env")


@app.command()
def version() -> None:
    """Print the package version."""

    console.print(__version__)


@app.command()
def up(adapter: str = typer.Option("local", help="local, mattermost, or switch")) -> None:
    """Check a room adapter and post one readiness line."""

    if adapter == "local":
        _up_local()
        return
    if adapter == "mattermost":
        from firedrill.adapters.mattermost import probe_mattermost

        _probe(probe_mattermost)
        return
    if adapter == "switch":
        from firedrill.adapters.switch import probe_switch

        _probe(probe_switch)
        return
    raise typer.BadParameter("adapter must be local, mattermost, or switch")


@app.command()
def consent(
    reviewer: str = typer.Argument(help="Reviewer id, for example avery"),
    line: str | None = typer.Option(None, "--line", help="Pass /optin without a prompt"),
) -> None:
    """Record /optin for one reviewer. The drill refuses to start until everyone has."""

    typed = line if line is not None else typer.prompt(f"{reviewer}, type /optin to consent")
    if typed.strip() != "/optin":
        console.print("consent was not recorded; the line has to be /optin")
        raise typer.Exit(code=1)
    with _live() as (auditor, _store, closers):
        try:
            result = auditor.command(reviewer, "/optin", _now())
        finally:
            _close(closers)
    if result != "opted-in":
        console.print(result)
        raise typer.Exit(code=1)
    console.print(f"{reviewer} opted in")


@app.command()
def start() -> None:
    """Post the answer-key commitment once every reviewer has sent /optin."""

    with _live() as (auditor, store, closers):
        try:
            existing = store.meta("commitment")
            if existing:
                console.print(f"drill already started sha256={existing}")
                return
            salt = "fd-salt-" + secrets.token_hex(4)
            digest = auditor.start(salt, _now())
        except ConsentError as exc:
            console.print(str(exc))
            raise typer.Exit(code=1) from exc
        finally:
            _close(closers)
    console.print(f"drill started sha256={digest}")


@app.command("run-demo")
def run_demo(offline: bool = typer.Option(False, "--offline", help="Use templates and do not call Grok.")) -> None:
    """Play 50 real items and 12 canaries with three simulated reviewers."""

    paths = default_paths()
    headline = play_demo(paths, offline=offline)
    console.print(headline)
    console.print(f"wrote {paths.report}")
    console.print(f"recorded {paths.recorded}")


@app.command()
def replay(
    recording: Path | None = typer.Argument(None, help="JSONL recording. Defaults to demo/recorded_drill.jsonl."),
) -> None:
    """Replay a recording and write the same report."""

    paths = default_paths()
    source = recording or paths.recorded
    if not source.is_file():
        console.print(f"no recording at {source}")
        raise typer.Exit(code=1)
    headline = replay_recording(paths, source)
    console.print(headline)
    console.print(f"wrote {paths.report}")


@app.command()
def report() -> None:
    """Print the headline and write report.md from the auditor database."""

    paths = default_paths()
    paths.ensure()
    store = AuditorStore(paths.drill_db)
    try:
        headline = write_report(store, paths.report)
    finally:
        store.close()
    console.print(headline)
    console.print(f"wrote {paths.report}")


@app.command()
def verify() -> None:
    """Recompute the commitment hash from the revealed key and salt."""

    paths = default_paths()
    bus = LocalAdapter(paths.room_db)
    try:
        text = "\n".join(message.body for message in bus.read_room())
    finally:
        bus.close()
    ok, detail = verify_reveal_text(text)
    if not ok:
        console.print(detail)
        raise typer.Exit(code=1)
    if f"COMMITMENT sha256={detail}" not in text:
        console.print("opening commitment does not match the reveal")
        raise typer.Exit(code=1)
    console.print(f"commitment ok sha256={detail}")


def _up_local() -> None:
    paths = default_paths()
    paths.ensure()
    bus = LocalAdapter(paths.room_db)
    try:
        existing = bus.read_room()
        if not existing:
            bus.post(
                author="system",
                role="system",
                body="Fire Drill local room is open. Messages keep author, role, timestamp, and thread.",
            )
            existing = bus.read_room()
        console.print(f"local room ready: {paths.room_db}")
        console.print(f"messages: {len(existing)}")
        last = existing[-1]
        console.print(f"last seq={last.seq} author={last.author} role={last.role} ts={last.ts}")
    finally:
        bus.close()


def _probe(func) -> None:  # type: ignore[no-untyped-def]
    try:
        console.print(func())
    except AdapterError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from exc


class _Live:
    def __init__(self) -> None:
        paths = default_paths()
        paths.ensure()
        if not paths.key_file.is_file():
            raise typer.BadParameter("auditor_private/key.json is missing. Run make setup.")
        secret = os.environ.get("WORKER_SECRET", "").strip()
        if not secret:
            raise typer.BadParameter("WORKER_SECRET is empty. Run make setup.")
        self.bus = LocalAdapter(paths.room_db)
        self.store = AuditorStore(paths.drill_db)
        self.registry = WorkerRegistry(paths.registry_db, secret.encode("utf-8"))
        flaws = {flaw.id: flaw for flaw in load_library(paths.library)}
        session = DrillSession(
            bus=self.bus,
            store=self.store,
            executor=Executor(self.registry, paths.work_repo if paths.work_repo.exists() else paths.sample_repo),
            required=[row["id"] for row in REVIEWERS],
            flaws=flaws,
            key_bytes=paths.key_file.read_bytes(),
        )
        self.auditor = Auditor(session)
        if self.store.meta("commitment"):
            session.started = True

    def __enter__(self) -> tuple[Auditor, AuditorStore, list[object]]:
        return self.auditor, self.store, [self.registry, self.store, self.bus]

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


def _live() -> _Live:
    return _Live()


def _close(closers: list[object]) -> None:
    for closer in closers:
        close = getattr(closer, "close", None)
        if close is not None:
            close()


