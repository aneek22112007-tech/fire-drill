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
    def key_file(self) -> Path:
        return self.auditor_dir / "key.json"

    @property
    def tokens_file(self) -> Path:
        return self.auditor_dir / "tokens.json"

    @property
    def drill_db(self) -> Path:
        return self.auditor_dir / "drill.db"

    @property
    def sample_repo(self) -> Path:
        env = os.environ.get("FIREDRILL_SAMPLE_REPO")
        if env:
            return Path(env)
        bundled = self.root / "sample_repo"
        if bundled.exists():
            return bundled
        return repo_root() / "sample_repo"

    @property
    def work_repo(self) -> Path:
        return self.data / "work_repo"

    @property
    def report(self) -> Path:
        return self.root / "report.md"

    @property
    def library(self) -> Path:
        bundled = self.root / "canaries" / "library.yaml"
        if bundled.exists():
            return bundled
        return repo_root() / "canaries" / "library.yaml"

    @property
    def recorded(self) -> Path:
        return self.root / "demo" / "recorded_drill.jsonl"

    def ensure(self) -> None:
        self.data.mkdir(parents=True, exist_ok=True)
        self.auditor_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.auditor_dir, 0o700)
        self.recorded.parent.mkdir(parents=True, exist_ok=True)


def default_paths() -> DrillPaths:
    override = os.environ.get("FIREDRILL_ROOT", "").strip()
    if override:
        return DrillPaths(root=Path(override).resolve())
    return DrillPaths(root=repo_root())
