"""Review metrics. Every figure used in the report comes from these functions."""

from __future__ import annotations

from dataclasses import dataclass, field

from firedrill.models import Decision


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


