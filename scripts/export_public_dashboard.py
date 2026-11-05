"""Export aggregate offline-drill metrics for the static public site.

The committed landing page and assets are preserved. This script writes only
public/data/metrics.json, public/report.md, and the embedded fallback in
public/index.html. It never exports request IDs, flaw IDs, tokens, or key data.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "report.md"
OUT = ROOT / "public"
FORBIDDEN = re.compile(r"flaw_id|request_id|AUDITOR_TOKEN|CANARY_INGEST_TOKEN|key\.json", re.I)


def ensure_report() -> str:
    if not REPORT.is_file():
        subprocess.run([sys.executable, "-m", "firedrill", "run-demo", "--offline"], cwd=ROOT, check=True)
    return REPORT.read_text(encoding="utf-8")


def sections(text: str) -> tuple[str, dict[str, str]]:
    match = re.search(r"\*\*(.+?)\*\*", text)
    headline = match.group(1) if match else ""
    parts: dict[str, str] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        parts[title.strip()] = body.strip()
    return headline, parts


def bullets(body: str) -> list[str]:
    return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]


def number(value: str | int | float) -> int | float:
    if isinstance(value, (int, float)):
        return value
    cleaned = value.strip().rstrip("%s")
    parsed = float(cleaned)
    return int(parsed) if parsed.is_integer() else parsed


def values(items: list[str]) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for item in items:
        key, separator, value = item.partition(":")
        if separator:
            result[key.strip()] = number(value)
    return result


def adaptation(item: str) -> dict[str, str]:
    match = re.match(r"`([^`]+)` \(([^)]+)\): (.+)", item)
    if not match:
        raise ValueError(f"Unexpected adaptation format: {item}")
    kind, reviewer, description = match.groups()
    return {"kind": kind, "reviewer": reviewer, "description": description}


def parse_report(text: str) -> dict[str, object]:
    headline, parts = sections(text)
    canaries = values(bullets(parts["Canaries"]))
    times = values(bullets(parts["Median times"]))
    reviewers = []
    for item in bullets(parts["Reviewers"]):
        name, _, rest = item.partition(":")
        fields = dict(re.findall(r"(decisions|canary catch rate|median canary|median real|correlation|flat) ([^,]+)", rest))
        reviewers.append({
            "name": name.strip(),
            "decisions": number(fields["decisions"]),
            "catch_rate": number(fields["canary catch rate"]),
            "median_canary_seconds": number(fields["median canary"]),
            "median_real_seconds": number(fields["median real"]),
            "complexity_correlation": number(fields["correlation"]),
            "flat": fields["flat"].strip() == "true",
        })
    mast_modes = []
    for item in bullets(parts["Catch rate by MAST mode"]):
        label, _, rate = item.rpartition(":")
        code, _, name = label.strip().partition(" ")
        mast_modes.append({"code": code, "name": name, "catch_rate": number(rate)})
    adaptations = [adaptation(item) for item in bullets(parts["Adaptations"])]
    counts = Counter(item["kind"] for item in adaptations)
    injected = int(canaries["Injected"])
    caught = int(canaries["Caught"])
    return {
        "schema_version": 1,
        "drill": {"id": "drill-001", "title": "Recorded offline oversight drill", "recorded": True},
        "source": "recorded-offline-demo",
        "headline": headline,
        "canaries": {
            "injected": injected,
            "caught": caught,
            "missed": injected - caught,
            "catch_rate": number(canaries["Catch rate"]),
            "executed": 0,
        },
        "items": {"total": int(canaries["Items in the drill"]), "real": int(canaries["Items in the drill"]) - injected},
        "review_times": {
            "canary_seconds": number(times["Canaries"]),
            "real_seconds": number(times["Real items"]),
            "complexity_correlation": number(times["Correlation of review time with complexity"]),
        },
        "mast_modes": mast_modes,
        "reviewers": reviewers,
        "flags": bullets(parts["Flags"]),
        "adaptations": adaptations,
        "adaptation_counts": [{"kind": kind, "count": count} for kind, count in counts.most_common()],
        "recommendation": parts["Recommended next change"].strip(),
        "limits": parts["Limits"].strip(),
        "safety": {"consent_first": True, "canaries_execute": False, "private_misses": True, "aggregate_export_only": True},
    }


def build_fallback(index: str, data: dict[str, object]) -> str:
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    pattern = r'(<script id="metrics-fallback" type="application/json">).*?(</script>)'
    replacement = rf"\g<1>{serialized}\g<2>"
    updated, count = re.subn(pattern, replacement, index, flags=re.S)
    if count != 1:
        raise ValueError("index.html must contain exactly one metrics-fallback script")
    return updated


def main() -> None:
    text = ensure_report()
    data = parse_report(text)
    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    index_path = OUT / "index.html"
    index = build_fallback(index_path.read_text(encoding="utf-8"), data)
    outputs = {
        OUT / "data" / "metrics.json": serialized,
        OUT / "report.md": text,
        index_path: index,
    }
    for path, content in outputs.items():
        if FORBIDDEN.search(content):
            raise SystemExit(f"refusing to publish {path}: contains private material")
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
    print(f"wrote {OUT / 'data' / 'metrics.json'} ({len(data['adaptations'])} aggregate adaptations)")
    print("updated embedded metrics fallback in public/index.html")


if __name__ == "__main__":
    main()
