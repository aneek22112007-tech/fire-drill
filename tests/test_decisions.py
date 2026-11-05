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


