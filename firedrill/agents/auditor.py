"""Auditor agent. This process is the only one that reads the answer key."""

from __future__ import annotations

from firedrill.adapters.base import RoomBus
from firedrill.session import DrillSession


class Auditor:
    def __init__(self, session: DrillSession) -> None:
        self._session = session
        self.bus: RoomBus = session.bus

    def start(self, salt: str, ts: str) -> str:
        return self._session.start(salt, ts)

    def reveal(self, ts: str) -> str:
        return self._session.reveal(ts)

    def command(self, reviewer: str, line: str, ts: str) -> str:
        return self._session.command(reviewer, line, ts)

    def ingest_commands(self) -> list[str]:
        """Apply /approve, /reject, /explain, and /optin lines read from the room bus."""

        return self._session.ingest_commands()
