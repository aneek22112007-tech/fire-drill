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


def coefficient_of_variation(values: list[float]) -> float | None:
    """Population coefficient of variation. A constant series is 0."""

    if not values:
        return None
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return (variance ** 0.5) / mean


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    spread_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    spread_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if spread_x == 0 or spread_y == 0:
        return None
    return numerator / (spread_x * spread_y)


@dataclass
class ReviewerMetrics:
    reviewer: str
    decisions: int
    catch_rate: float | None
    median_canary_s: float | None
    median_real_s: float | None
    correlation: float | None
    flat: bool


@dataclass
class DrillMetrics:
    items: int
    canaries_injected: int
    canaries_caught: int
    catch_rate: float | None
    median_canary_s: float | None
    median_real_s: float | None
    correlation: float | None
    by_reviewer: list[ReviewerMetrics] = field(default_factory=list)
    by_mast: dict[str, float | None] = field(default_factory=dict)
    flat_reviewers: list[str] = field(default_factory=list)


def _closing(decisions: list[Decision]) -> dict[str, Decision]:
    closed: dict[str, Decision] = {}
    for decision in decisions:
        if decision.action in {"approve", "reject"} and decision.request_id not in closed:
            closed[decision.request_id] = decision
    return closed


