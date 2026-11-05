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


