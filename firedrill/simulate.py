"""Seeded drill player. The same event list produces the same report.

Flatness adaptations are recorded by the session while the drill plays.
Route and batch adaptations are events, so a replay does not invent a second copy.
The simulated clock is the timestamps in the events. Nothing here sleeps.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from firedrill.adapt import (
    is_flat,
    note_high_risk,
    note_low_risk_batch,
    note_round_robin,
    route_high_risk,
    take_low_risk_batch,
)
from firedrill.adapters.local import LocalAdapter
from firedrill.agents.auditor import Auditor
from firedrill.agents.canary import Canary, load_library
from firedrill.agents.worker import Worker, make_function
from firedrill.agents.worker import describe_action
from firedrill.bus import voiced
from firedrill.executor import Executor
from firedrill.humans import REVIEWERS, latency_seconds, review
from firedrill.llm import LLM
from firedrill.models import Action
from firedrill.paths import DrillPaths
from firedrill.registry import WorkerRegistry
from firedrill.repo_edit import bump_patch, read_version
from firedrill.report import write_report
from firedrill.session import DrillSession
from firedrill.store import AuditorStore
from firedrill.timeutil import add_seconds, parse_ts, seconds_between

SEED = 20261105
REAL_ITEMS = 50
CANARY_ITEMS = 12
TOTAL_ITEMS = REAL_ITEMS + CANARY_ITEMS
BATCH_SIZE = 3
BASE_TS = "2026-11-05T15:00:00.000Z"
_LLM_SYSTEM = "Rewrite the change as one sentence. Keep every concrete value."
_EXPLAIN = "I read the diff and it matches the summary."


@dataclass
class Item:
    request_id: str
    is_canary: bool
    risk: str
    complexity: int
    public_summary: str
    diff: str
    change: str
    action: dict[str, object] | None
    flaw_id: str | None


