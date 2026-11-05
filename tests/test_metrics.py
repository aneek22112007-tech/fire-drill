"""M6: hand-checked metrics, and flatness forces explain-back."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from firedrill.adapt import is_flat, note_high_risk, note_low_risk_batch, route_high_risk, take_low_risk_batch
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


