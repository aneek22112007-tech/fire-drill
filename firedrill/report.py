"""The drill report and the private dashboard. Numbers are computed, never fixed."""

from __future__ import annotations

import html
from pathlib import Path

from firedrill.metrics import DrillMetrics, compute_metrics
from firedrill.store import AuditorStore

LIMITS = (
    "Limits: small sample; demonstrates the method, not statistical significance. "
    "Three simulated or live reviewers and one repository are enough to show the "
    "measurement, and they are not enough to estimate a population rate."
)


