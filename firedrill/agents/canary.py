"""Canary agent. Posts a normal-looking request and forwards the flaw id once.

The agent does not keep the request-to-flaw map. The callable it is given is
the auditor ingest, which is the only place the map is stored.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from firedrill.adapters.local import LocalAdapter
from firedrill.agents.worker import new_request_id
from firedrill.bus import CHANGE_AGENT, CHANGE_ROLE, format_approval
from firedrill.models import ApprovalRequest, Flaw


def load_library(path: Path) -> list[Flaw]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [Flaw.model_validate(item) for item in raw["flaws"]]


class Canary:
    def __init__(self, bus: LocalAdapter, submit_mapping: Callable[[str, str], None]) -> None:
        self.bus = bus
        self._submit_mapping = submit_mapping

