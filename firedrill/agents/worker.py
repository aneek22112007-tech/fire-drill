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
