"""M8: offline demo, replay, reviewers, and the Switch template."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from firedrill.adapters.base import AdapterError
from firedrill.adapters.local import LocalAdapter
from firedrill.adapters.mattermost import missing_token_message
from firedrill.adapters.switch import filter_arguments
from firedrill.agents.canary import load_library
from firedrill.agents.worker import describe_action
from firedrill.bus import voiced
from firedrill.cli import app
from firedrill.commands import CATCH_MARK, MISS_MARK
from firedrill.commitment import verify_reveal_text
from firedrill.humans import latency_seconds, review
from firedrill.llm import LLM
from firedrill.metrics import compute_metrics
from firedrill.models import Action
from firedrill.paths import DrillPaths
from firedrill.report import LIMITS, headline
from firedrill.repo_edit import preview_diff
from firedrill.simulate import SEED, build_events, play, read_events, write_events
from firedrill.store import AuditorStore

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_careful_catches_every_flaw_and_approves_a_real_bump():
    flaws = load_library(ROOT / "canaries" / "library.yaml")
    obvious = {"fake-secret", "destructive-migration", "removed-test", "skipped-verification"}
    for flaw in flaws:
        summary = flaw.template.format(change=flaw.summary)
        diff = flaw.diff.strip() + "\n"
        action, reason = review("careful", summary, diff)
        assert action == "reject", flaw.id
        assert reason
        average, _average_reason = review("average", summary, diff)
        assert average == ("reject" if flaw.id in obvious else "approve")
        assert review("rushed", summary, diff)[0] == "approve"
    action = Action(kind="version_bump", version="1.0.1")
    change, _risk, complexity = describe_action(action)
    diff = preview_diff(ROOT / "sample_repo", action)
    assert review("careful", voiced(change), diff) == ("approve", "")
    assert latency_seconds("rushed", complexity) < 8


def test_offline_llm_does_not_call_the_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("offline mode called the network")

    monkeypatch.setattr("firedrill.llm.httpx.post", explode)
    monkeypatch.setenv("XAI_API_KEY", "present-but-must-not-be-sent")
    assert LLM(offline=True).complete("system", "  Keep this sentence.  ") == "Keep this sentence."


def test_switch_filter_refuses_unpublished_argument_names():
    schema = {"parameters": {"properties": {"room_id": {}, "content": {}}}}
    assert filter_arguments(schema, {"room_id": "room-1", "content": "hello"}) == {
        "room_id": "room-1",
        "content": "hello",
    }
    with pytest.raises(AdapterError):
        filter_arguments(schema, {"room_id": "room-1", "target": "someone"})
    with pytest.raises(AdapterError):
        filter_arguments({}, {"room_id": "room-1"})


def test_mattermost_instructions_do_not_guess_a_password():
    text = missing_token_message("http://127.0.0.1:8065")
    assert "MM_TOKEN" in text
    assert "does not guess an admin password" in text
    assert "admin123" not in text


def test_room_template_matches_the_switch_language():
    document = yaml.safe_load((ROOT / "switch" / "room-template.yaml").read_text(encoding="utf-8"))
    assert document["version"] == 1
    agents = document["agents"]
    assert {agent["name"] for agent in agents} == {"worker", "canary", "auditor"}
    addressing = {agent["name"]: agent["addressing"] for agent in agents}
    assert addressing == {"worker": "anyone", "canary": "owner", "auditor": "owner"}
    allowed = {"claude", "codex", "opencode", "antigravity", "cursor"}
    for agent in agents:
        assert agent["instructions"].strip()
        assert agent["auto_approve"] is False
        assert agent["provider"] == "{provider}"
        assert agent["location"] == "{location}"
        assert agent["directory"].strip()
    assert set(document["params"]["provider"]["default"]) <= allowed
    instructions = document["room"]["instructions"].lower()
    assert "canaries never execute" in instructions
    assert "only the auditor accesses the answer key" in instructions
    roles = {role["name"]: role for role in document["room"]["roles"]}
    assert roles["answer-key"]["exclusive"] is True
    assert "canaries never execute" in document["kickoff"].lower()


def test_seed_events_are_deterministic(tmp_path):
    paths = DrillPaths(root=ROOT)
    first = build_events(paths, offline=True, seed=SEED)
    second = build_events(paths, offline=True, seed=SEED)
    assert first == second
    assert sum(1 for event in first if event["kind"] == "real") == 50
    assert sum(1 for event in first if event["kind"] == "canary") == 12
    target = tmp_path / "recorded.jsonl"
    write_events(target, first)
    assert read_events(target) == first
    assert read_events(ROOT / "demo" / "recorded_drill.jsonl") == first


