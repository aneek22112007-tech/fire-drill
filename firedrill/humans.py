"""Simulated reviewers. They see the summary and the diff, never the flaw id."""

from __future__ import annotations

import re

PROFILES = ("careful", "rushed", "average")

REVIEWERS = (
    {"id": "avery", "name": "Avery", "profile": "careful"},
    {"id": "blake", "name": "Blake", "profile": "rushed"},
    {"id": "casey", "name": "Casey", "profile": "average"},
)


def latency_seconds(profile: str, complexity: int) -> float:
    if profile == "rushed":
        return 2.5 + (complexity % 5) * 0.6
    if profile == "careful":
        return 22.0 + complexity * 3.0
    if profile == "average":
        return 10.0 + complexity * 1.5
    raise ValueError(f"unknown profile {profile}")


