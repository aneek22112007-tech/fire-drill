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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "report.md"
OUT = ROOT / "public"
sys.path.insert(0, str(ROOT))
from firedrill.public_metrics import FORBIDDEN, parse_report  # noqa: E402,F401


def ensure_report() -> str:
    if not REPORT.is_file():
        subprocess.run([sys.executable, "-m", "firedrill", "run-demo", "--offline"], cwd=ROOT, check=True)
    return REPORT.read_text(encoding="utf-8")


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
