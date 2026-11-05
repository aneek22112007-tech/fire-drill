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


