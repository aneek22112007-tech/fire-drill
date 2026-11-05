"""Review metrics. Every figure used in the report comes from these functions."""

from __future__ import annotations

from dataclasses import dataclass, field

from firedrill.models import Decision, DrillConfig


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


def _rate(caught: int, total: int) -> float | None:
    if total == 0:
        return None
    return caught / total


def compute_metrics(
    requests: list[dict[str, object]],
    decisions: list[Decision],
    settings: DrillConfig | None = None,
) -> DrillMetrics:
    from firedrill.adapt import is_flat

    closed = _closing(decisions)
    canaries = [row for row in requests if row.get("is_canary")]
    reals = [row for row in requests if not row.get("is_canary")]
    caught = [
        row
        for row in canaries
        if row["id"] in closed and closed[str(row["id"])].action == "reject"
    ]
    canary_times = [_latency(row, closed) for row in canaries if row["id"] in closed]
    real_times = [_latency(row, closed) for row in reals if row["id"] in closed]
    paired = _pairs(requests, closed)

    by_mast: dict[str, float | None] = {}
    modes = sorted({str(row.get("mast_mode")) for row in canaries if row.get("mast_mode")})
    for mode in modes:
        group = [row for row in canaries if row.get("mast_mode") == mode]
        group_caught = sum(
            1
            for row in group
            if row["id"] in closed and closed[str(row["id"])].action == "reject"
        )
        by_mast[mode] = _rate(group_caught, len(group))

    reviewers = sorted({decision.reviewer for decision in decisions if decision.action in {"approve", "reject"}})
    by_reviewer: list[ReviewerMetrics] = []
    flat_reviewers: list[str] = []
    for reviewer in reviewers:
        own = [decision for decision in closed.values() if decision.reviewer == reviewer]
        own_ids = {decision.request_id for decision in own}
        own_canaries = [row for row in canaries if row["id"] in own_ids]
        own_reals = [row for row in reals if row["id"] in own_ids]
        own_caught = sum(1 for row in own_canaries if closed[str(row["id"])].action == "reject")
        own_pairs = _pairs(requests, {item.request_id: item for item in own})
        times = [decision.latency_s for decision in own]
        flat = is_flat(times, settings)
        if flat:
            flat_reviewers.append(reviewer)
        by_reviewer.append(
            ReviewerMetrics(
                reviewer=reviewer,
                decisions=len(own),
                catch_rate=_rate(own_caught, len(own_canaries)),
                median_canary_s=median([_latency(row, closed) for row in own_canaries]),
                median_real_s=median([_latency(row, closed) for row in own_reals]),
                correlation=pearson([pair[0] for pair in own_pairs], [pair[1] for pair in own_pairs]),
                flat=flat,
            )
        )

    return DrillMetrics(
        items=len(requests),
        canaries_injected=len(canaries),
        canaries_caught=len(caught),
        catch_rate=_rate(len(caught), len(canaries)),
        median_canary_s=median([value for value in canary_times if value is not None]),
        median_real_s=median([value for value in real_times if value is not None]),
        correlation=pearson([pair[0] for pair in paired], [pair[1] for pair in paired]),
        by_reviewer=by_reviewer,
        by_mast=by_mast,
        flat_reviewers=flat_reviewers,
    )


def _latency(row: dict[str, object], closed: dict[str, Decision]) -> float:
    return closed[str(row["id"])].latency_s


def _pairs(requests: list[dict[str, object]], closed: dict[str, Decision]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in requests:
        decision = closed.get(str(row["id"]))
        if decision is None:
            continue
        pairs.append((float(row["complexity"]), decision.latency_s))
    return pairs
