"""Auditor agent. This process is the only one that reads the answer key."""

from __future__ import annotations

from firedrill.session import DrillSession


class Auditor:
    def __init__(self, session: DrillSession) -> None:
        self._session = session

