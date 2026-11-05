"""M7: the report and the private dashboard use computed numbers."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from firedrill.metrics import compute_metrics
from firedrill.models import Decision
from firedrill.report import LIMITS, headline, write_report
from firedrill.service import create_app
from firedrill.store import AuditorStore


