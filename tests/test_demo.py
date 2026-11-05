"""M8: offline demo, replay, reviewers, and the Switch template."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from firedrill.adapters.base import AdapterError
from firedrill.adapters.local import LocalAdapter
from firedrill.adapters.mattermost import missing_token_message
from firedrill.adapters.switch import filter_arguments
from firedrill.agents.canary import load_library
from firedrill.agents.worker import describe_action
from firedrill.bus import voiced
from firedrill.cli import app
from firedrill.commands import CATCH_MARK, MISS_MARK
from firedrill.commitment import verify_reveal_text
from firedrill.humans import latency_seconds, review
from firedrill.llm import LLM
from firedrill.metrics import compute_metrics
from firedrill.models import Action
from firedrill.paths import DrillPaths
from firedrill.report import LIMITS, headline
from firedrill.repo_edit import preview_diff
from firedrill.simulate import SEED, build_events, play, read_events, write_events
from firedrill.store import AuditorStore

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


