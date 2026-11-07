"""Live API: auth, limits, secret safety, and mocked-provider runs."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from firedrill.llm import LLM, LLMError
from firedrill.simulate import run_demo
from firedrill.web import create_app

SECRET = "xai-TEST-SECRET-should-never-leak"
ADMIN = "admin-test-token"


def provider(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    body = json.loads(request.content)
    assert body["max_tokens"] > 0
    return httpx.Response(200, json={"choices": [{"message": {"content": "Rewritten: " + body["messages"][1]["content"]}}]})


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("FIREDRILL_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("FIREDRILL_RUN_COOLDOWN_SECONDS", "0")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    return monkeypatch


def wait(client, run_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.2)
    raise AssertionError("run did not finish")


def mocked_drill(handler):
    def drill(paths, offline, llm):
        if not offline:
            llm._client = provider(handler)
        run_demo(paths, offline=offline, llm=llm)

    return drill


def all_text(client, run_id):
    parts = [client.get(p).text for p in ("/api/health", "/api/runs", f"/api/runs/{run_id}", "/api/metrics/latest")]
    return "\n".join(parts)


def test_live_run_with_mocked_provider(env, tmp_path, caplog):
    env.setenv("XAI_API_KEY", SECRET)
    client = TestClient(create_app(tmp_path, drill=mocked_drill(ok_handler)))
    assert client.get("/api/health").json()["live_llm_available"] is True
    r = client.post("/api/runs", json={"mode": "live"}, headers={"Authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 202, r.text
    run = wait(client, r.json()["id"])
    assert run["status"] == "succeeded", run
    assert run["mode"] == "live-llm" and run["provider"] == "xai"
    assert run["llm_calls"] == 50
    assert run["switch_room"] is False and run["reviewers"] == "simulated"
    m = client.get("/api/metrics/latest").json()
    assert m["source"] == "live-llm" and m["canaries"]["executed"] == 0 and m["canaries"]["injected"] == 12
    text = all_text(client, run["id"]) + caplog.text
    for forbidden in (SECRET, "flaw_id", "request_id", "fd-"):
        assert forbidden not in text
    assert not (tmp_path / "work" / run["id"]).exists(), "answer key must not outlive the run"


@pytest.mark.parametrize(
    "handler,expected",
    [
        (lambda r: httpx.Response(401, json={"error": f"bad key {SECRET}"}), "HTTP 401"),
        (lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}), "empty completion"),
        (lambda r: httpx.Response(200, text="not json"), "unexpected payload"),
    ],
)
def test_provider_errors_fail_safely(env, tmp_path, handler, expected):
    env.setenv("XAI_API_KEY", SECRET)
    client = TestClient(create_app(tmp_path, drill=mocked_drill(handler)))
    r = client.post("/api/runs", json={"mode": "live"}, headers={"Authorization": f"Bearer {ADMIN}"})
    run = wait(client, r.json()["id"])
    assert run["status"] == "failed" and expected in run["error"]
    assert SECRET not in json.dumps(run)
    assert client.get("/api/metrics/latest").status_code == 404


def test_timeout_and_budget(env):
    env.setenv("XAI_API_KEY", SECRET)
    env.setenv("LLM_MAX_CALLS_PER_RUN", "1")

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    llm = LLM(client=provider(slow))
    with pytest.raises(LLMError, match="timed out"):
        llm.complete("s", "u")
    with pytest.raises(LLMError, match="budget"):
        llm.complete("s", "u")
    assert SECRET not in repr(llm)


def test_offline_run_is_labelled(env, tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/health").json()["live_llm_available"] is False
    assert client.post("/api/runs", json={"mode": "live"}, headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 503
    r = client.post("/api/runs", json={"mode": "offline"}, headers={"Authorization": f"Bearer {ADMIN}"})
    run = wait(client, r.json()["id"])
    assert run["status"] == "succeeded" and run["mode"] == "offline-template" and run["llm_calls"] == 0
    assert client.get("/api/metrics/latest").json()["source"] == "offline-template"


def test_auth_and_input_bounds(env, tmp_path):
    client = TestClient(create_app(tmp_path, drill=lambda *a: None))
    assert client.post("/api/runs", json={"mode": "offline"}).status_code == 401
    assert client.post("/api/runs", json={"mode": "offline"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/runs", json={"mode": "rm -rf"}, headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 422
    assert client.post("/api/runs", json={"mode": "offline", "x": 1}, headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 422
    big = client.post("/api/runs", content="x" * 5000, headers={"Authorization": f"Bearer {ADMIN}", "Content-Type": "application/json"})
    assert big.status_code == 413
    assert client.get("/api/runs/../../etc/passwd").status_code == 404
    assert client.get("/api/runs/run-zzz").status_code == 404
    for _ in range(10):
        client.post("/api/runs", json={"mode": "offline"}, headers={"Authorization": "Bearer nope"})
    assert client.post("/api/runs", json={"mode": "offline"}, headers={"Authorization": f"Bearer {ADMIN}"}).status_code == 429


def test_runs_disabled_without_admin_token(env, tmp_path):
    env.delenv("FIREDRILL_ADMIN_TOKEN")
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/health").json()["runs_enabled"] is False
    assert client.post("/api/runs", json={"mode": "offline"}, headers={"Authorization": "Bearer x"}).status_code == 403


def test_concurrency_cooldown_and_cap(env, tmp_path):
    import threading

    gate = threading.Event()
    client = TestClient(create_app(tmp_path, drill=lambda *a: gate.wait(5)))
    h = {"Authorization": f"Bearer {ADMIN}"}
    first = client.post("/api/runs", json={"mode": "offline"}, headers=h)
    assert first.status_code == 202
    assert client.post("/api/runs", json={"mode": "offline"}, headers=h).status_code == 409
    gate.set()
    wait(client, first.json()["id"])
    env.setenv("FIREDRILL_MAX_RUNS_PER_DAY", "1")
    capped = TestClient(create_app(tmp_path / "b", drill=lambda *a: None))
    assert capped.post("/api/runs", json={"mode": "offline"}, headers=h).status_code == 202
    assert capped.post("/api/runs", json={"mode": "offline"}, headers=h).status_code == 429


def test_static_site_served_with_headers(env, tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.get("/")
    assert r.status_code == 200 and "data-live-panel" in r.text
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/js/live.js").status_code == 200
    assert client.get("/auditor_private/key.json").status_code == 404
