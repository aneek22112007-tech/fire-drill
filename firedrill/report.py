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
            "until the flatness rule clears: median at least 8 seconds, and, once they "
            "have 5 or more decisions, either a coefficient of variation of at least 0.25 "
            "or a median of at least 15 seconds."
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
                f"- Flatness flag for {reviewer}: median under 8s across at least 3 decisions, "
                "or CV under 0.25 with median under 15s across at least 5 decisions."
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


def write_report(store: AuditorStore, path: Path) -> str:
    metrics = compute_metrics(store.requests(), store.decisions())
    text = render_report(metrics, store.adaptations())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return headline(metrics)


def render_dashboard(store: AuditorStore) -> str:
    metrics = compute_metrics(store.requests(), store.decisions())
    adaptations = store.adaptations()
    rows = []
    for mode, rate in metrics.by_mast.items():
        rows.append(
            f"<tr><td>{html.escape(mode)}</td><td>{html.escape(fmt_rate(rate))}</td></tr>"
        )
    mast_table = "\n".join(rows) or "<tr><td colspan='2'>No canaries were classified.</td></tr>"
    flags = (
        ", ".join(html.escape(name) for name in metrics.flat_reviewers)
        or "none"
    )
    adaptation_items = "\n".join(
        f"<li><code>{html.escape(str(note['rule']))}</code> "
        f"{html.escape(str(note['reason']))}</li>"
        for note in adaptations
    ) or "<li>No adaptations.</li>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fire Drill dashboard</title>
<style>
body {{ font-family: Georgia, serif; margin: 2rem auto; max-width: 46rem; color: #1c1917; }}
h1 {{ font-size: 1.6rem; }}
.headline {{ font-size: 1.15rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #d6d3d1; text-align: left; padding: 0.35rem; }}
.limits {{ background: #f5f5f4; padding: 0.8rem 1rem; }}
</style>
</head>
<body>
<h1>Fire Drill</h1>
<p class="headline">{html.escape(headline(metrics))}</p>
<h2>Canaries</h2>
<p>Injected {metrics.canaries_injected}. Caught {metrics.canaries_caught}. Catch rate {html.escape(fmt_rate(metrics.catch_rate))}.</p>
<h2>Median times</h2>
<p>Canaries {html.escape(fmt_seconds(metrics.median_canary_s))}s. Real items {html.escape(fmt_seconds(metrics.median_real_s))}s. Correlation with complexity {html.escape(fmt_corr(metrics.correlation))}.</p>
<h2>Catch rate by MAST mode</h2>
<table>
<tr><th>Mode</th><th>Catch rate</th></tr>
{mast_table}
</table>
<h2>Flags</h2>
<p>{flags}</p>
<h2>Adaptations</h2>
<ul>
{adaptation_items}
</ul>
<h2>Recommended next change</h2>
<p>{html.escape(recommend(metrics))}</p>
<h2>Limits</h2>
<p class="limits">{html.escape(LIMITS)}</p>
</body>
</html>
"""
