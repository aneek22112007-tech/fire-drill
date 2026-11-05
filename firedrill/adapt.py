"""Workflow changes the auditor applies, each with a reason that is logged."""

from __future__ import annotations

from dataclasses import dataclass

from firedrill.metrics import coefficient_of_variation, median


