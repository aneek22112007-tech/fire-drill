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


