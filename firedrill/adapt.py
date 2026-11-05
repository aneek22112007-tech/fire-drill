"""Workflow changes the auditor applies, each with a reason that is logged."""

from __future__ import annotations

from dataclasses import dataclass

from firedrill.metrics import coefficient_of_variation, median


def is_flat(
    times: list[float],
    *,
    cv_limit: float = 0.25,
    min_decisions: int = 5,
    median_limit: float = 8.0,
) -> bool:
    """True when review times are suspiciously uniform or suspiciously fast."""

    if not times:
        return False
    middle = median(times)
    if middle is not None and middle < median_limit:
        return True
    if len(times) >= min_decisions:
        spread = coefficient_of_variation(times)
        if spread is not None and spread < cv_limit:
            return True
    return False


