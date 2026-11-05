"""M3: canary requests match the worker schema and the executor refuses them."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from firedrill.adapters.local import LocalAdapter
from firedrill.agents.canary import Canary, load_library
from firedrill.agents.worker import Worker
from firedrill.bus import SUMMARY_TEMPLATE
from firedrill.executor import Executor, ExecutorRefusal
from firedrill.registry import WorkerRegistry

ROOT = Path(__file__).resolve().parents[1]
HEADER = re.compile(
    r"^Approval request fd-[0-9a-f]{8}\n"
    r"Summary: .+\n"
    r"Risk: (low|medium|high)\n"
    r"Complexity: ([1-9]|10)\n"
    r"Diff:\n```diff\n",
    re.S,
)


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv("WORKER_SECRET", "test-worker-secret")
    return b"test-worker-secret"


def test_library_has_twelve_distinct_flaws():
    flaws = load_library(ROOT / "canaries" / "library.yaml")
    assert len(flaws) == 12
    assert len({flaw.id for flaw in flaws}) == 12
    for flaw in flaws:
        assert flaw.template == SUMMARY_TEMPLATE
        assert flaw.tell
        assert flaw.mast_mode
        assert "AKIA" not in flaw.tell or flaw.id == "fake-secret"


def test_canary_id_is_refused_and_mapping_is_not_kept(tmp_path, secret):
    flaws = load_library(ROOT / "canaries" / "library.yaml")
    bus = LocalAdapter(tmp_path / "room.db")
    inbox: dict[str, str] = {}
    canary = Canary(bus, lambda request_id, flaw_id: inbox.__setitem__(request_id, flaw_id))
    request = canary.post_flaw(flaws[2], request_id="fd-aabbccdd")

    registry = WorkerRegistry(tmp_path / "registry.db", secret)
    executor = Executor(registry, tmp_path)
    assert registry.contains(request.id) is False
    with pytest.raises(ExecutorRefusal, match="not in the worker registry"):
        executor.execute(request.id)

    assert inbox == {"fd-aabbccdd": "fake-secret"}
    assert "fake-secret" not in repr(vars(canary))
    assert "flaw" not in vars(canary)

    body = bus.read_room()[0].body
    assert HEADER.match(body)
    assert "fake-secret" not in body
    assert "AKIAFAKEFAKEFAKE0000" in body
    assert "canary" not in body.lower()

    source = (ROOT / "firedrill" / "agents" / "canary.py").read_text(encoding="utf-8")
    assert "WORKER_SECRET" not in source
    assert "WorkerRegistry" not in source
    registry.close()
    bus.close()


def test_worker_and_canary_messages_share_a_shape(tmp_path, secret):
    repo = tmp_path / "repo"
    repo.mkdir()
    # The shape check uses the posted text, not the repository.
    bus = LocalAdapter(tmp_path / "room.db")
    registry = WorkerRegistry(tmp_path / "registry.db", secret)
    sample = ROOT / "sample_repo"
    worker = Worker(registry, bus, sample)
    action = worker.action_version_bump()
    summary, risk, complexity = worker.describe(action)
    worker.propose(action, summary=summary, risk=risk, complexity=complexity, request_id="fd-11111111")

    flaws = load_library(ROOT / "canaries" / "library.yaml")
    Canary(bus, lambda *_args: None).post_flaw(flaws[0], request_id="fd-22222222")
    bodies = [message.body for message in bus.read_room()]
    assert len(bodies) == 2
    assert all(HEADER.match(body) for body in bodies)
    assert bodies[0].splitlines()[0].startswith("Approval request fd-")
    assert bodies[1].splitlines()[0].startswith("Approval request fd-")
    bus.close()
    registry.close()
