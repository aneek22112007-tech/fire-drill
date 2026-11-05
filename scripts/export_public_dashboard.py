"""Export a read-only public dashboard from report.md.

Writes public/index.html and public/report.md. Contains only aggregate
results: no answer key, no flaw ids, no request-to-flaw mappings, no tokens.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "report.md"
OUT = ROOT / "public"
FORBIDDEN = re.compile(r"flaw_id|AUDITOR_TOKEN|CANARY_INGEST_TOKEN|key\.json", re.I)


def ensure_report() -> str:
    if not REPORT.is_file():
        subprocess.run([sys.executable, "-m", "firedrill", "run-demo", "--offline"], cwd=ROOT, check=True)
    return REPORT.read_text(encoding="utf-8")


def sections(text: str) -> tuple[str, dict[str, str]]:
    headline = ""
    m = re.search(r"\*\*(.+?)\*\*", text)
    if m:
        headline = m.group(1)
    parts: dict[str, str] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        parts[title.strip()] = body.strip()
    return headline, parts


def bullets(body: str) -> list[str]:
    return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]


def inline(s: str) -> str:
    s = html.escape(s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def kv_table(items: list[str]) -> str:
    rows = []
    for it in items:
        k, _, v = it.partition(":")
        rows.append(f"<tr><th>{inline(k)}</th><td>{inline(v.strip())}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def reviewers_table(items: list[str]) -> str:
    head = "<tr><th>Reviewer</th><th>Decisions</th><th>Canary catch</th><th>Median canary</th><th>Median real</th><th>Flat</th></tr>"
    rows = []
    for it in items:
        name, _, rest = it.partition(":")
        f = dict(re.findall(r"(decisions|canary catch rate|median canary|median real|flat) ([^,]+)", rest))
        flat = f.get("flat", "").strip()
        cls = ' class="flag"' if flat == "true" else ""
        rows.append(
            f"<tr{cls}><td>{inline(name)}</td><td>{inline(f.get('decisions',''))}</td>"
            f"<td>{inline(f.get('canary catch rate',''))}</td><td>{inline(f.get('median canary',''))}</td>"
            f"<td>{inline(f.get('median real',''))}</td><td>{inline(flat)}</td></tr>"
        )
    return "<table>" + head + "".join(rows) + "</table>"


def adaptations_summary(items: list[str]) -> str:
    kinds = Counter(re.match(r"`([^`]+)`", i).group(1) for i in items if i.startswith("`"))
    explain = [i for i in items if "flatness_explain_back" in i]
    out = "<table><tr><th>Adaptation</th><th>Count</th></tr>"
    out += "".join(f"<tr><td><code>{html.escape(k)}</code></td><td>{v}</td></tr>" for k, v in kinds.most_common())
    out += "</table>"
    if explain:
        out += "<h3>Explain-back triggers</h3><ul>" + "".join(f"<li>{inline(e)}</li>" for e in explain) + "</ul>"
    return out


def build(text: str) -> str:
    headline, p = sections(text)
    body = [
        f'<p class="headline">{inline(headline)}</p>',
        "<section><h2>Canaries</h2>" + kv_table(bullets(p.get("Canaries", ""))) + "</section>",
        "<section><h2>Median review times</h2>" + kv_table(bullets(p.get("Median times", ""))) + "</section>",
        "<section><h2>Catch rate by MAST failure mode</h2>" + kv_table(bullets(p.get("Catch rate by MAST mode", ""))) + "</section>",
        "<section><h2>Reviewers</h2>" + reviewers_table(bullets(p.get("Reviewers", ""))) + "</section>",
        "<section><h2>Flags</h2><ul>" + "".join(f"<li>{inline(b)}</li>" for b in bullets(p.get("Flags", ""))) + "</ul></section>",
        "<section><h2>Adaptations</h2>" + adaptations_summary(bullets(p.get("Adaptations", ""))) + "</section>",
        "<section><h2>Recommended next change</h2><p>" + inline(p.get("Recommended next change", "")) + "</p></section>",
        '<section class="limits"><h2>Limits</h2><p>' + inline(p.get("Limits", "")) + "</p></section>",
    ]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fire Drill: Chaos Engineering for Human Oversight</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:880px;margin:2rem auto;padding:0 1rem;color:#1d2330;background:#fafbfc;line-height:1.5}}
h1{{margin-bottom:.2rem}} .sub{{color:#5b6475;margin-top:0}}
.headline{{font-size:1.25rem;font-weight:600;background:#fff4e5;border-left:4px solid #f08c00;padding:1rem}}
section{{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:.5rem 1rem 1rem;margin:1rem 0}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:.35rem .5rem;border-bottom:1px solid #eef0f3}}
tr.flag td{{background:#fff0f0}} code{{background:#f1f3f5;padding:0 .25rem;border-radius:3px}}
.limits{{background:#f4f6f8}} footer{{color:#7a8394;font-size:.85rem;margin:2rem 0}}
</style></head><body>
<h1>Fire Drill</h1><p class="sub">Chaos engineering for human oversight of AI agents. Read-only results from a recorded offline drill.</p>
{''.join(body)}
<footer>Aggregate results only. The answer key stays private to the Auditor. Source: <a href="https://github.com/aneek22112007-tech/fire-drill">github.com/aneek22112007-tech/fire-drill</a></footer>
</body></html>
"""


def main() -> None:
    text = ensure_report()
    page = build(text)
    for name, content in (("index.html", page), ("report.md", text)):
        if FORBIDDEN.search(content):
            raise SystemExit(f"refusing to publish {name}: contains private material")
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    (OUT / "report.md").write_text(text, encoding="utf-8")
    print(f"wrote {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
