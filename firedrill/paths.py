"""Repository paths. Tests pass an explicit root so they never touch the demo state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass
class DrillPaths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def room_db(self) -> Path:
        return self.data / "room.db"

    @property
    def registry_db(self) -> Path:
        return self.data / "worker_registry.db"

    @property
    def auditor_dir(self) -> Path:
        return self.root / "auditor_private"

    @property
