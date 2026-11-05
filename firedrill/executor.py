"""The only place that applies an edit. Canary ids are refused."""

from __future__ import annotations

from pathlib import Path

from firedrill.registry import RegistryError, WorkerRegistry
from firedrill.repo_edit import apply_action


class ExecutorRefusal(RuntimeError):
    pass


class Executor:
    def __init__(self, registry: WorkerRegistry, repo: Path) -> None:
        self.registry = registry
        self.repo = Path(repo)

