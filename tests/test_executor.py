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
