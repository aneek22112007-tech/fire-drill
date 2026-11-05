"""M5: consent is required, and canary misses stay in a private DM."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from firedrill.adapters.local import LocalAdapter
from firedrill.agents.canary import Canary, load_library
from firedrill.agents.worker import Worker
from firedrill.commands import CATCH_MARK, MISS_MARK
from firedrill.executor import Executor
from firedrill.registry import WorkerRegistry
from firedrill.session import ConsentError, DrillSession
from firedrill.store import AuditorStore

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_repo"


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_SECRET", "test-worker-secret")
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo)
    bus = LocalAdapter(tmp_path / "room.db")
    store = AuditorStore(tmp_path / "drill.db")
    registry = WorkerRegistry(tmp_path / "registry.db", b"test-worker-secret")
    flaws = {flaw.id: flaw for flaw in load_library(ROOT / "canaries" / "library.yaml")}
    key = {"version": 1, "drill_key": "k"}
    key_bytes = (json.dumps(key) + "\n").encode()
    session = DrillSession(
        bus=bus,
        store=store,
        executor=Executor(registry, repo),
        required=["avery", "blake", "casey"],
        flaws=flaws,
        key_bytes=key_bytes,
    )
    return {
        "repo": repo,
        "bus": bus,
        "store": store,
        "registry": registry,
        "session": session,
        "worker": Worker(registry, bus, repo),
        "canary": Canary(bus, store.add_mapping),
        "flaws": flaws,
    }


def _room_text(bus: LocalAdapter) -> str:
    return "\n".join(message.body for message in bus.read_room())


def test_drill_refuses_to_start_without_full_consent(world):
    session = world["session"]
    session.command("avery", "/optin", "2026-11-05T15:00:00.000Z")
    with pytest.raises(ConsentError, match="blake"):
        session.start("salt", "2026-11-05T15:00:01.000Z")
    assert session.started is False
    session.command("blake", "/optin", "2026-11-05T15:00:02.000Z")
    session.command("casey", "/optin", "2026-11-05T15:00:03.000Z")
    digest = session.start("salt", "2026-11-05T15:00:04.000Z")
    assert session.started is True
    assert digest in _room_text(world["bus"])


def test_canary_miss_is_private_and_real_approval_applies(world):
    session: DrillSession = world["session"]
    bus: LocalAdapter = world["bus"]
    repo: Path = world["repo"]
    for person, ts in (
        ("avery", "2026-11-05T15:00:00.000Z"),
        ("blake", "2026-11-05T15:00:01.000Z"),
        ("casey", "2026-11-05T15:00:02.000Z"),
    ):
        session.command(person, "/optin", ts)
    session.start("salt", "2026-11-05T15:00:03.000Z")

    flaw = world["flaws"]["staging-vs-prod"]
    canary_request = world["canary"].post_flaw(flaw, request_id="fd-aaaa0001", ts="2026-11-05T15:01:00.000Z")
    before = (repo / "config.yaml").read_text(encoding="utf-8")
    assert session.command("avery", "/approve fd-aaaa0001", "2026-11-05T15:01:20.000Z") == "approve"
    assert (repo / "config.yaml").read_text(encoding="utf-8") == before
    room = _room_text(bus)
    assert MISS_MARK not in room
    assert flaw.tell not in room
    assert "staging-vs-prod" not in room
    dm = "\n".join(message.body for message in bus.read_channel("dm:avery"))
    assert MISS_MARK in dm
    assert flaw.tell in dm
    assert "not executed" in dm

    caught = world["canary"].post_flaw(
        world["flaws"]["fake-secret"],
        request_id="fd-aaaa0002",
        ts="2026-11-05T15:02:00.000Z",
    )
    assert session.command(
        "blake",
        f"/reject {caught.id} the diff contains a credential",
        "2026-11-05T15:02:30.000Z",
    ) == "reject"
    blake_dm = "\n".join(message.body for message in bus.read_channel("dm:blake"))
    assert CATCH_MARK in blake_dm
    assert "Nice catch" in blake_dm
    assert CATCH_MARK not in _room_text(bus)

    worker = world["worker"]
    action = worker.action_version_bump()
    summary, risk, complexity = worker.describe(action)
    real = worker.propose(
        action,
        summary=summary,
        risk=risk,
        complexity=complexity,
        request_id="fd-bbbb0001",
        ts="2026-11-05T15:03:00.000Z",
    )
    assert session.command("casey", f"/approve {real.id}", "2026-11-05T15:03:15.000Z") == "approve"
    assert (repo / "VERSION").read_text(encoding="utf-8").strip() == "1.0.1"
    assert canary_request.id not in {
        decision.request_id
        for decision in world["store"].decisions()
        if decision.action == "approve" and decision.request_id == real.id
    }


