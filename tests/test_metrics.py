"""M6: hand-checked metrics, and flatness forces explain-back."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from firedrill.adapt import (
    assign_canary,
    decisions_phrase,
    is_flat,
    note_canary,
    note_high_risk,
    note_low_risk_batch,
    route_high_risk,
    take_low_risk_batch,
)
from firedrill.adapters.local import LocalAdapter
from firedrill.agents.worker import Worker
from firedrill.executor import Executor
from firedrill.metrics import coefficient_of_variation, compute_metrics, median, pearson
from firedrill.models import Decision
from firedrill.registry import WorkerRegistry
from firedrill.session import DrillSession
from firedrill.store import AuditorStore

ROOT = Path(__file__).resolve().parents[1]


def _request(request_id: str, *, canary: bool, complexity: int, mast: str | None, risk: str = "low") -> dict:
    return {
        "id": request_id,
        "summary": request_id,
        "diff": "",
        "risk": risk,
        "complexity": complexity,
        "created_ts": "2026-11-05T15:00:00.000Z",
        "is_canary": 1 if canary else 0,
        "flaw_id": "x" if canary else None,
        "mast_mode": mast,
    }


def _decision(request_id: str, reviewer: str, action: str, latency: float) -> Decision:
    return Decision(
        request_id=request_id,
        reviewer=reviewer,
        action=action,  # type: ignore[arg-type]
        reason="",
        timestamp="2026-11-05T15:00:10.000Z",
        latency_s=latency,
    )


def test_metrics_on_a_handmade_fixture():
    requests = [
        _request("fd-00000001", canary=True, complexity=1, mast="3.2 No or Incomplete Verification"),
        _request("fd-00000002", canary=True, complexity=2, mast="3.2 No or Incomplete Verification"),
        _request("fd-00000003", canary=True, complexity=3, mast="1.1 Disobey Task Specification"),
        _request("fd-00000004", canary=True, complexity=4, mast="1.1 Disobey Task Specification"),
        _request("fd-00000005", canary=False, complexity=2, mast=None),
        _request("fd-00000006", canary=False, complexity=5, mast=None),
    ]
    decisions = [
        _decision("fd-00000001", "avery", "reject", 10),
        _decision("fd-00000002", "avery", "approve", 20),
        _decision("fd-00000003", "blake", "reject", 30),
        _decision("fd-00000004", "blake", "approve", 40),
        _decision("fd-00000005", "avery", "approve", 5),
        _decision("fd-00000006", "blake", "approve", 15),
    ]
    metrics = compute_metrics(requests, decisions)
    assert metrics.items == 6
    assert metrics.canaries_injected == 4
    assert metrics.canaries_caught == 2
    assert metrics.catch_rate == 0.5
    assert metrics.median_canary_s == 25
    assert metrics.median_real_s == 10
    expected = pearson([1, 2, 3, 4, 2, 5], [10, 20, 30, 40, 5, 15])
    assert metrics.correlation == expected
    assert expected is not None and abs(expected - 0.4689450951470155) < 1e-12
    assert metrics.by_mast["3.2 No or Incomplete Verification"] == 0.5
    assert metrics.by_mast["1.1 Disobey Task Specification"] == 0.5
    avery = next(item for item in metrics.by_reviewer if item.reviewer == "avery")
    assert avery.catch_rate == 0.5
    assert avery.median_canary_s == 15
    assert avery.median_real_s == 5
    assert median([10, 20, 30, 40]) == 25
    assert pearson([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1)
    assert coefficient_of_variation([10, 10, 10, 10, 10]) == 0


def test_flatness_rules():
    assert is_flat([2, 2, 2, 2, 2]) is True
    assert is_flat([2.5, 2.6, 2.4, 2.7, 2.5]) is True
    assert is_flat([7, 7, 7]) is True
    assert is_flat([10, 10, 10, 10, 10]) is True
    assert is_flat([10, 10, 10, 10]) is False
    assert is_flat([7]) is False
    assert is_flat([9]) is False
    assert is_flat([9, 9, 9]) is False
    assert is_flat([30, 40, 50, 60, 70]) is False
    careful = [28, 31, 34, 37, 40]
    assert coefficient_of_variation(careful) < 0.25
    assert median(careful) > 15
    assert is_flat(careful) is False
    spread = [30, 32, 34, 36, 38]
    assert coefficient_of_variation(spread) < 0.25
    assert is_flat(spread) is False
    assert decisions_phrase(1) == "1 decision"
    assert decisions_phrase(3) == "3 decisions"


def test_canary_routing_shares_the_load_and_breaks_ties_toward_careful():
    reviewers = ["avery", "blake", "casey"]
    counts = {name: 0 for name in reviewers}
    chosen = []
    for _ in range(12):
        name = assign_canary(reviewers, counts, "avery")
        chosen.append(name)
        counts[name] += 1
    assert counts == {"avery": 4, "blake": 4, "casey": 4}
    assert chosen[0] == "avery"
    first = note_canary("avery", 0)
    second = note_canary("avery", 1)
    assert first.reason != second.reason
    assert "canary 1" in first.reason
    assert "canary 2" in second.reason


def test_routing_and_batch_notes():
    last = {"avery": "2026-11-05T15:00:10.000Z", "blake": None, "casey": "2026-11-05T15:00:01.000Z"}
    assert route_high_risk(["avery", "blake", "casey"], last) == "blake"
    note = note_high_risk(["avery", "blake", "casey"], last)
    assert note.reviewer == "blake"
    assert "oldest last decision" in note.reason
    pending = ["a", "b", "c", "d"]
    assert take_low_risk_batch(pending, 3) == ["a", "b", "c"]
    assert pending == ["d"]
    batch = note_low_risk_batch(3)
    assert batch.rule == "batch_low_risk"
    assert "3" in batch.reason


def test_flatness_triggers_explain_back(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKER_SECRET", "test-worker-secret")
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "sample_repo", repo)
    bus = LocalAdapter(tmp_path / "room.db")
    store = AuditorStore(tmp_path / "drill.db")
    registry = WorkerRegistry(tmp_path / "registry.db", b"test-worker-secret")
    session = DrillSession(
        bus=bus,
        store=store,
        executor=Executor(registry, repo),
        required=["blake"],
        flaws={},
        key_bytes=b"key\n",
    )
    worker = Worker(registry, bus, repo)
    session.command("blake", "/optin", "2026-11-05T15:00:00.000Z")
    session.start("salt", "2026-11-05T15:00:01.000Z")

    def propose(action, request_id: str, ts: str):
        summary, risk, complexity = worker.describe(action)
        return worker.propose(
            action,
            summary=summary,
            risk=risk,
            complexity=complexity,
            request_id=request_id,
            ts=ts,
        )

    opening = propose(worker.action_version_bump(), "fd-11111111", "2026-11-05T15:01:00.000Z")
    assert session.command("blake", f"/approve {opening.id}", "2026-11-05T15:01:03.000Z") == "approve"
    assert store.adaptations() == []
    second = propose(worker.action_function(1), "fd-22222222", "2026-11-05T15:02:00.000Z")
    assert session.command("blake", f"/approve {second.id}", "2026-11-05T15:02:03.000Z") == "approve"
    assert store.adaptations() == []
    third = propose(worker.action_config("feature_02", True), "fd-33333333", "2026-11-05T15:03:00.000Z")
    assert session.command("blake", f"/approve {third.id}", "2026-11-05T15:03:03.000Z") == "approve"
    flat = [row for row in store.adaptations() if row["rule"] == "flatness_explain_back"]
    assert len(flat) == 1
    assert "across 3 decisions" in str(flat[0]["reason"])
    assert "1 decisions" not in str(flat[0]["reason"])

    blocked = propose(worker.action_config("feature_03", True), "fd-44444444", "2026-11-05T15:04:00.000Z")
    assert session.command("blake", f"/approve {blocked.id}", "2026-11-05T15:04:03.000Z") == "explain-required"
    assert "feature_03" not in (repo / "config.yaml").read_text(encoding="utf-8")
    assert session.command("blake", f"/explain {blocked.id} the diff only sets a feature flag", "2026-11-05T15:04:04.000Z") == "explained"
    assert session.command("blake", f"/approve {blocked.id}", "2026-11-05T15:04:05.000Z") == "approve"
    assert "feature_03: true" in (repo / "config.yaml").read_text(encoding="utf-8")
    flat_after = [row for row in store.adaptations() if row["rule"] == "flatness_explain_back"]
    assert flat_after == flat
    bus.close()
    registry.close()
    store.close()
