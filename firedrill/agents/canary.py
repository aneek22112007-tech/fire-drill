"""Canary agent. Posts a normal-looking request and forwards the flaw id once.

The agent does not keep the request-to-flaw map. On the drill path the callable
POSTs {request_id, flaw_id} to the auditor service with the ingest token.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from firedrill.adapters.base import RoomBus
from firedrill.agents.worker import new_request_id
from firedrill.bus import CHANGE_AGENT, CHANGE_ROLE, format_approval
from firedrill.models import ApprovalRequest, Flaw


def load_library(path: Path) -> list[Flaw]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [Flaw.model_validate(item) for item in raw["flaws"]]


class Canary:
    def __init__(self, bus: RoomBus, submit_mapping: Callable[[str, str], None]) -> None:
        self.bus = bus
        self._submit_mapping = submit_mapping

    def post_flaw(
        self,
        flaw: Flaw,
        *,
        request_id: str | None = None,
        ts: str | None = None,
    ) -> ApprovalRequest:
        request_id = request_id or new_request_id()
        request = ApprovalRequest(
            id=request_id,
            summary=flaw.template.format(change=flaw.summary),
            diff=flaw.diff.strip() + "\n",
            risk=flaw.risk,
            complexity=flaw.complexity,
        )
        self.bus.post(
            author=CHANGE_AGENT,
            role=CHANGE_ROLE,
            body=format_approval(request),
            ts=ts,
        )
        self._submit_mapping(request.id, flaw.id)
        return request
