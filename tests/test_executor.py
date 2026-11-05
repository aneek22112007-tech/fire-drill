"""M2: an approved real edit applies and tests pass; a rejection leaves the tree alone."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from firedrill.adapters.local import LocalAdapter
from firedrill.agents.worker import Worker
from firedrill.executor import Executor, ExecutorRefusal
from firedrill.registry import WorkerRegistry
from firedrill.repo_edit import read_version

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_repo"


@pytest.fixture()
def secret(monkeypatch):
    monkeypatch.setenv("WORKER_SECRET", "test-worker-secret")
    return b"test-worker-secret"


def _copy_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(SAMPLE, dest)
    return dest


def _pytest(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_approved_version_bump_and_function(tmp_path, secret):
    repo = _copy_repo(tmp_path)
    bus = LocalAdapter(tmp_path / "room.db")
    registry = WorkerRegistry(tmp_path / "registry.db", secret)
    worker = Worker(registry, bus, repo)
    executor = Executor(registry, repo)

    bump = worker.action_version_bump()
    summary, risk, complexity = worker.describe(bump)
    request = worker.propose(bump, summary=summary, risk=risk, complexity=complexity)
    assert request.id.startswith("fd-")
    assert "1.0.1" in request.diff
    executor.execute(request.id)
    assert read_version(repo) == "1.0.1"

    added = worker.action_function(7)
    summary, risk, complexity = worker.describe(added)
    request = worker.propose(added, summary=summary, risk=risk, complexity=complexity)
    executor.execute(request.id)
    assert "def fn_07" in (repo / "src" / "samplelib" / "ops.py").read_text(encoding="utf-8")

    result = _pytest(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    bus.close()
    registry.close()


def test_rejected_request_leaves_repo_untouched(tmp_path, secret):
    repo = _copy_repo(tmp_path)
    before = (repo / "config.yaml").read_text(encoding="utf-8")
    bus = LocalAdapter(tmp_path / "room.db")
    registry = WorkerRegistry(tmp_path / "registry.db", secret)
    worker = Worker(registry, bus, repo)
    action = worker.action_config("feature_01", True)
    summary, risk, complexity = worker.describe(action)
    request = worker.propose(action, summary=summary, risk=risk, complexity=complexity)
    # A rejection never calls the executor.
    assert "feature_01" in request.diff
    assert (repo / "config.yaml").read_text(encoding="utf-8") == before
    bus.close()
    registry.close()


def test_executor_refuses_unregistered_id(tmp_path, secret):
    repo = _copy_repo(tmp_path)
    registry = WorkerRegistry(tmp_path / "registry.db", secret)
    executor = Executor(registry, repo)
    with pytest.raises(ExecutorRefusal, match="not in the worker registry"):
        executor.execute("fd-deadbeef")
    assert read_version(repo) == "1.0.0"
    registry.close()
