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
