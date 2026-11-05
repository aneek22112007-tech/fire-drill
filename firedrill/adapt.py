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


def route_high_risk(reviewers: list[str], last_decision_ts: dict[str, str | None]) -> str:
    """The reviewer whose last decision is oldest. No decision yet sorts first."""

    if not reviewers:
        raise ValueError("no reviewers to route to")

    def sort_key(reviewer: str) -> tuple[bool, str, str]:
        seen = last_decision_ts.get(reviewer)
        return (seen is not None, seen or "", reviewer)

    return min(reviewers, key=sort_key)


