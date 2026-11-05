"""Worker agent: real edits, signed registry entries, identical public requests."""

from __future__ import annotations

import random
import secrets
from pathlib import Path

from firedrill.adapters.local import LocalAdapter
from firedrill.bus import CHANGE_AGENT, CHANGE_ROLE, format_approval, voiced
from firedrill.models import Action, ApprovalRequest, Risk
from firedrill.registry import WorkerRegistry
from firedrill.repo_edit import bump_patch, preview_diff, read_version


def new_request_id(rng: random.Random | None = None) -> str:
    if rng is None:
        return "fd-" + secrets.token_hex(4)
    return "fd-" + f"{rng.getrandbits(32):08x}"


class Worker:
    def __init__(self, registry: WorkerRegistry, bus: LocalAdapter, repo: Path) -> None:
        self.registry = registry
        self.bus = bus
        self.repo = Path(repo)

    def propose(
        self,
        action: Action,
        *,
        summary: str,
        risk: Risk,
        complexity: int,
        request_id: str | None = None,
        ts: str | None = None,
    ) -> ApprovalRequest:
        request_id = request_id or new_request_id()
        diff = preview_diff(self.repo, action)
        self.registry.register(request_id, action)
        request = ApprovalRequest(
            id=request_id,
            summary=voiced(summary),
            diff=diff,
            risk=risk,
            complexity=complexity,
        )
        self.bus.post(
            author=CHANGE_AGENT,
            role=CHANGE_ROLE,
            body=format_approval(request),
            ts=ts,
        )
        return request

    def action_version_bump(self) -> Action:
        return Action(kind="version_bump", version=bump_patch(read_version(self.repo)))

