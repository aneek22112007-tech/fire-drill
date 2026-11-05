"""M7: the report and the private dashboard use computed numbers."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from firedrill.metrics import compute_metrics
from firedrill.models import Decision
from firedrill.report import LIMITS, headline, write_report
from firedrill.service import create_app
from firedrill.store import AuditorStore


def test_report_uses_store_numbers_and_dashboard_is_private(tmp_path):
    store = AuditorStore(tmp_path / "drill.db")
    store.upsert_request(
        request_id="fd-00000001",
        summary="canary",
        diff="diff",
        risk="high",
        complexity=4,
        created_ts="2026-11-05T15:00:00.000Z",
        flaw_id="fake-secret",
        mast_mode="3.3 Incorrect Verification",
    )
    store.upsert_request(
        request_id="fd-00000002",
        summary="real",
        diff="diff",
        risk="low",
        complexity=2,
        created_ts="2026-11-05T15:01:00.000Z",
    )
    store.record_decision(
        Decision(
            request_id="fd-00000001",
            reviewer="avery",
            action="reject",
            reason="secret",
            timestamp="2026-11-05T15:00:30.000Z",
            latency_s=30,
        )
    )
    store.record_decision(
        Decision(
            request_id="fd-00000002",
            reviewer="blake",
            action="approve",
            reason="",
            timestamp="2026-11-05T15:01:12.000Z",
            latency_s=12,
        )
    )
    store.record_adaptation(
        ts="2026-11-05T15:01:12.000Z",
        rule="route_high_risk",
        reviewer="avery",
        reason="High-risk item routed to avery, the reviewer with the oldest last decision.",
    )
    metrics = compute_metrics(store.requests(), store.decisions())
    expected = headline(metrics)
    path = tmp_path / "report.md"
    assert write_report(store, path) == expected
    text = path.read_text(encoding="utf-8")
    assert expected in text
    assert "Injected 1 canaries across 2 items; caught 1." in text
    assert "Median review time 30s on canaries vs 12s on real items." in text
    assert "3.3 Incorrect Verification" in text
    assert "route_high_risk" in text
    assert LIMITS in text
    assert "small sample; demonstrates the method, not statistical significance" in text

    private = tmp_path / "auditor_private"
    private.mkdir()
    key = private / "key.json"
    key.write_text(json.dumps({"version": 1, "drill_key": "k"}) + "\n", encoding="utf-8")
    tokens = private / "tokens.json"
    tokens.write_text(
        json.dumps({"auditor_token": "auditor-token", "canary_ingest_token": "ingest-token"}),
        encoding="utf-8",
    )
    client = TestClient(create_app(key, tokens, tmp_path / "drill.db"))
    denied = client.get("/dashboard")
    assert denied.status_code == 401
    allowed = client.get("/dashboard", headers={"Authorization": "Bearer auditor-token"})
    assert allowed.status_code == 200
    assert "Injected 1 canaries across 2 items; caught 1." in allowed.text
    assert "small sample; demonstrates the method, not statistical significance" in allowed.text
    store.close()
