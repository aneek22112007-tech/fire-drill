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
