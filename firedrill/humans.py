"""Simulated reviewers. They see the summary and the diff, never the flaw id."""

from __future__ import annotations

import re

PROFILES = ("careful", "rushed", "average")

REVIEWERS = (
    {"id": "avery", "name": "Avery", "profile": "careful"},
    {"id": "blake", "name": "Blake", "profile": "rushed"},
    {"id": "casey", "name": "Casey", "profile": "average"},
)


