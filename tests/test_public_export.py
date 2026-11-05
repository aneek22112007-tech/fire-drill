"""The public site receives only real aggregate drill results."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("public_export", ROOT / "scripts" / "export_public_dashboard.py")
public_export = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(public_export)


def test_export_matches_recorded_report():
    data = public_export.parse_report((ROOT / "report.md").read_text())
    assert data["canaries"] == {"injected": 12, "caught": 5, "missed": 7, "catch_rate": 41.7, "executed": 0}
    assert data["items"] == {"total": 62, "real": 50}
    assert data["review_times"]["canary_seconds"] == 15.2
    assert len(data["reviewers"]) == 3
    assert len(data["mast_modes"]) == 7
    assert len(data["adaptations"]) == 45
    assert sum(item["count"] for item in data["adaptation_counts"]) == 45


def test_json_and_embedded_fallback_are_identical():
    public = (ROOT / "public" / "data" / "metrics.json").read_text()
    html = (ROOT / "public" / "index.html").read_text()
    embedded = html.split('<script id="metrics-fallback" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(public) == json.loads(embedded)


def test_export_contains_no_private_identifiers():
    for path in (ROOT / "public" / "data" / "metrics.json", ROOT / "public" / "report.md", ROOT / "public" / "index.html"):
        assert public_export.FORBIDDEN.search(path.read_text()) is None


def test_export_preserves_two_act_site():
    html = (ROOT / "public" / "index.html").read_text()
    for marker in ('id="landing-view"', 'id="dashboard-view"', 'data-replay-modal', 'data-mast-list', 'data-reviewers-body'):
        assert marker in html
    assert 'prefers-reduced-motion' in (ROOT / "public" / "css" / "site.css").read_text()


def test_report_parser_escapes_no_executable_markup():
    # Data is serialized as JSON and all dynamic DOM renderers escape report strings.
    js = (ROOT / "public" / "js" / "site.js").read_text()
    assert "const escapeHTML" in js
    assert "innerHTML = state.metrics" not in js
