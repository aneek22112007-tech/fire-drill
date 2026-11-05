"""Workflow changes the auditor applies, each with a reason that is logged."""

from __future__ import annotations

from dataclasses import dataclass

from firedrill.metrics import coefficient_of_variation, median
from firedrill.models import DrillConfig


def decisions_phrase(count: int) -> str:
    """'1 decision' or 'N decisions'. The adaptation log uses this wording."""

    noun = "decision" if count == 1 else "decisions"
    return f"{count} {noun}"


def is_flat(times: list[float], settings: DrillConfig | None = None) -> bool:
    """True when review times are fast, or both fast and uniform.

    The two clauses and their thresholds come from DrillConfig.
    """

    config = settings or DrillConfig(reviewers=[])
    if not times:
        return False
    middle = median(times)
    if middle is None:
        return False
    count = len(times)
    if count >= config.flat_fast_min_decisions and middle < config.flat_fast_median_seconds:
        return True
    if count >= config.flat_consistent_min_decisions:
        spread = coefficient_of_variation(times)
        if (
            spread is not None
            and spread < config.flat_consistent_cv
            and middle < config.flat_consistent_median_seconds
        ):
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


def take_low_risk_batch(pending: list[object], batch_size: int) -> list[object]:
    if batch_size < 1 or len(pending) < batch_size:
        return []
    batch = pending[:batch_size]
    del pending[:batch_size]
    return batch


@dataclass(frozen=True)
class AdaptationNote:
    rule: str
    reviewer: str | None
    reason: str


def note_high_risk(reviewers: list[str], last_decision_ts: dict[str, str | None]) -> AdaptationNote:
    chosen = route_high_risk(reviewers, last_decision_ts)
    return AdaptationNote(
        rule="route_high_risk",
        reviewer=chosen,
        reason=(
            f"High-risk item routed to {chosen}, the reviewer with the oldest last decision."
        ),
    )


def note_low_risk_batch(count: int) -> AdaptationNote:
    return AdaptationNote(
        rule="batch_low_risk",
        reviewer=None,
        reason=f"Batched {count} low-risk items so reviewers see them together.",
    )


def note_round_robin(reviewer: str, seen: int = 0) -> AdaptationNote:
    return AdaptationNote(
        rule="route_medium",
        reviewer=reviewer,
        reason=(
            f"Medium-risk item routed to {reviewer} "
            f"(medium {seen + 1} for that reviewer) by round-robin."
        ),
    )


def assign_canary(reviewers: list[str], counts: dict[str, int], careful: str) -> str:
    """Give the canary to whoever has seen the fewest. Ties go to the careful reviewer."""

    if not reviewers:
        raise ValueError("no reviewers to route to")
    fewest = min(counts.get(name, 0) for name in reviewers)
    tied = [name for name in reviewers if counts.get(name, 0) == fewest]
    if careful in tied:
        return careful
    return tied[0]


def note_canary(reviewer: str, seen: int) -> AdaptationNote:
    """seen is how many canaries that reviewer already has. The count keeps each row distinct."""

    return AdaptationNote(
        rule="route_canary",
        reviewer=reviewer,
        reason=(
            f"Canary routed to {reviewer} (canary {seen + 1} for that reviewer). "
            "Ties go to the careful reviewer."
        ),
    )
