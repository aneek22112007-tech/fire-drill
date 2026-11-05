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


