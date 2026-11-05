"""The drill report and the private dashboard. Numbers are computed, never fixed."""

from __future__ import annotations

import html
from pathlib import Path

from firedrill.metrics import DrillMetrics, compute_metrics
from firedrill.store import AuditorStore

LIMITS = (
    "Limits: small sample; demonstrates the method, not statistical significance. "
    "Three simulated or live reviewers and one repository are enough to show the "
    "measurement, and they are not enough to estimate a population rate."
)


def fmt_seconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}"


def fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def fmt_corr(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def headline(metrics: DrillMetrics) -> str:
    return (
        f"Injected {metrics.canaries_injected} canaries across {metrics.items} items; "
        f"caught {metrics.canaries_caught}. "
        f"Median review time {fmt_seconds(metrics.median_canary_s)}s on canaries vs "
        f"{fmt_seconds(metrics.median_real_s)}s on real items."
    )


def recommend(metrics: DrillMetrics) -> str:
    if metrics.flat_reviewers:
        name = metrics.flat_reviewers[0]
        return (
            f"Require {name} to explain the diff in one sentence before every approval "
            "until their review-time coefficient of variation is at least 0.25 and "
            "their median review time is at least 8 seconds."
        )
    weak = [
        (mode, rate)
        for mode, rate in metrics.by_mast.items()
        if rate is not None and rate < 0.5
    ]
    if weak:
        mode, rate = sorted(weak, key=lambda item: item[1])[0]
        return (
            f"Add a checklist item for {mode} before high-risk approvals. "
            f"Catch rate on that mode is {fmt_rate(rate)}."
        )
    return (
        "Keep the canary rate and compare the next drill's catch rate "
        "before changing the approval UI."
    )


def render_report(metrics: DrillMetrics, adaptations: list[dict[str, object]]) -> str:
    lines = [
        "# Fire Drill report",
        "",
        f"**{headline(metrics)}**",
        "",
        "## Canaries",
        "",
        f"- Injected: {metrics.canaries_injected}",
        f"- Caught: {metrics.canaries_caught}",
        f"- Catch rate: {fmt_rate(metrics.catch_rate)}",
        f"- Items in the drill: {metrics.items}",
        "",
        "## Median times",
        "",
        f"- Canaries: {fmt_seconds(metrics.median_canary_s)}s",
        f"- Real items: {fmt_seconds(metrics.median_real_s)}s",
        f"- Correlation of review time with complexity: {fmt_corr(metrics.correlation)}",
        "",
        "## Catch rate by MAST mode",
        "",
    ]
    if metrics.by_mast:
        for mode, rate in metrics.by_mast.items():
            lines.append(f"- {mode}: {fmt_rate(rate)}")
    else:
        lines.append("- No canaries were classified.")
    lines.extend(["", "## Flags", ""])
    if metrics.flat_reviewers:
        for reviewer in metrics.flat_reviewers:
            lines.append(
                f"- Flatness flag for {reviewer}: review times were uniform or faster than 8 seconds."
            )
    else:
        lines.append("- No flatness flags.")
    lines.extend(["", "## Reviewers", ""])
    if metrics.by_reviewer:
        for item in metrics.by_reviewer:
            lines.append(
                f"- {item.reviewer}: decisions {item.decisions}, "
                f"canary catch rate {fmt_rate(item.catch_rate)}, "
                f"median canary {fmt_seconds(item.median_canary_s)}s, "
                f"median real {fmt_seconds(item.median_real_s)}s, "
                f"correlation {fmt_corr(item.correlation)}, "
                f"flat {str(item.flat).lower()}"
            )
    else:
        lines.append("- No decisions yet.")
    lines.extend(["", "## Adaptations", ""])
    if adaptations:
        for note in adaptations:
            reviewer = note.get("reviewer") or "room"
            lines.append(f"- `{note['rule']}` ({reviewer}): {note['reason']}")
    else:
        lines.append("- No adaptations.")
    lines.extend(
        [
            "",
            "## Recommended next change",
            "",
            recommend(metrics),
            "",
            "## Limits",
            "",
            LIMITS,
            "",
        ]
    )
    return "\n".join(lines)


