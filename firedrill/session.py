"""Consent, decisions, and private canary feedback."""

from __future__ import annotations

from firedrill.adapters.local import LocalAdapter
from firedrill.commands import catch_dm, miss_dm, parse_approval, parse_command
from firedrill.adapt import is_flat
from firedrill.commitment import commitment_hash, commitment_message, reveal_message
from firedrill.executor import Executor, ExecutorRefusal
from firedrill.metrics import median
from firedrill.models import Decision, Flaw
from firedrill.store import AuditorStore
from firedrill.timeutil import seconds_between


class ConsentError(RuntimeError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            "drill refused to start; missing /optin from: " + ", ".join(missing)
        )


class DrillSession:
    def __init__(
        self,
        *,
        bus: LocalAdapter,
        store: AuditorStore,
        executor: Executor,
        required: list[str],
        flaws: dict[str, Flaw],
        key_bytes: bytes,
    ) -> None:
        self.bus = bus
        self.store = store
        self.executor = executor
        self.required = list(required)
        self.flaws = flaws
        self.key_bytes = key_bytes
        self.started = False
        self._seen_seq = 0
        self.needs_explain: set[str] = set()
        self.explained_ready: set[str] = set()

