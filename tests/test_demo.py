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


