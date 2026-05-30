"""FastAPI endpoint tests.

Validation, status codes, and contract shape. Behavioral tests that need
the LLM proxy or BGE-M3 weights are skipped automatically when the env
isn't configured — the route-existence + request-validation surface
is fully covered without them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from klerk.api.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """Fresh app per test, with KLERK_STATE_DIR isolated to a tmp path."""
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path / ".klerk"))
    monkeypatch.setenv("KLERK_DRIVE_MANIFEST", str(tmp_path / ".klerk" / "drive-manifest.json"))
    # Ensure no leftover LLM creds bleed in for tests that expect "unconfigured".
    return TestClient(create_app())


# ─── /health ─────────────────────────────────────────────────────────────────
def test_health_returns_200_and_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "version" in body
    assert "checks" in body
    assert body["checks"]["bge_m3"] == "lazy"


def test_health_latency_headers_present(client):
    r = client.get("/health")
    assert "x-klerk-total-ms" in {k.lower() for k in r.headers}
    assert "x-klerk-ttft-ms" in {k.lower() for k in r.headers}


def test_health_marks_degraded_without_creds(client, monkeypatch):
    monkeypatch.delenv("LITELLM_KEY", raising=False)
    monkeypatch.delenv("CF_CLIENT_ID", raising=False)
    r = client.get("/health")
    assert r.json()["checks"]["nemotron_proxy"] == "unconfigured"


# ─── /chat ───────────────────────────────────────────────────────────────────
def test_chat_returns_503_without_creds(client, monkeypatch):
    monkeypatch.delenv("LITELLM_KEY", raising=False)
    r = client.post("/chat", json={"query": "what is the parental leave policy?"})
    assert r.status_code == 503
    assert "LITELLM_KEY" in r.json()["detail"]


def test_chat_validates_empty_query(client):
    r = client.post("/chat", json={"query": ""})
    assert r.status_code == 422


def test_chat_validates_locale_enum(client):
    r = client.post("/chat", json={"query": "hi", "locale": "fr"})
    assert r.status_code == 422


def test_chat_validates_k_bounds(client):
    r = client.post("/chat", json={"query": "hi", "k": 100})
    assert r.status_code == 422


def test_chat_streams_orchestrator_events_and_persists_session(client, monkeypatch):
    """With creds present and the orchestrator mocked, /chat streams the SSE
    events through and persists the turn under a fresh session id."""
    monkeypatch.setenv("LITELLM_KEY", "sk-test")

    async def fake_arun(query, *, session_id, locale, history):
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}
        yield {"event": "token", "data": json.dumps({"text": "Parental leave is 90 days [hr:0]."})}
        yield {"event": "citations", "data": json.dumps({"citations": ["hr:0"], "confidence": 0.4})}
        yield {"event": "done", "data": json.dumps({"ttft_ms": 10, "total_ms": 20, "n_chunks": 1})}

    from klerk.agent import orchestrator

    monkeypatch.setattr(orchestrator, "arun", fake_arun)

    with client.stream("POST", "/chat", json={"query": "parental leave?"}) as r:
        assert r.status_code == 200
        raw = "".join(r.iter_text())

    assert "event: session" in raw
    assert "event: token" in raw
    assert "event: citations" in raw
    assert "event: done" in raw

    # The turn was persisted under the auto-issued session id.
    from klerk.api.session import get_store

    sessions = get_store().recent_sessions(limit=5)
    assert len(sessions) == 1
    turns = get_store().load(sessions[0])
    assert turns[0].role == "user" and turns[0].content == "parental leave?"
    assert turns[1].role == "assistant" and "Parental leave is 90 days" in turns[1].content


def test_chat_reuses_supplied_session_id(client, monkeypatch):
    monkeypatch.setenv("LITELLM_KEY", "sk-test")

    async def fake_arun(query, *, session_id, locale, history):
        yield {"event": "token", "data": json.dumps({"text": "ok"})}
        yield {"event": "done", "data": json.dumps({"n_chunks": 0})}

    from klerk.agent import orchestrator

    monkeypatch.setattr(orchestrator, "arun", fake_arun)

    with client.stream("POST", "/chat", json={"query": "hi", "session_id": "fixed-123"}) as r:
        assert r.status_code == 200
        "".join(r.iter_text())

    from klerk.api.session import get_store

    assert get_store().exists("fixed-123")


# ─── /ingest ─────────────────────────────────────────────────────────────────
def test_ingest_path_requires_path(client):
    r = client.post("/ingest", json={"source": "path"})
    assert r.status_code == 422


def test_ingest_returns_202_with_run_id(client):
    r = client.post("/ingest", json={"source": "path", "path": "/nonexistent"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["run_id"].startswith("ing_")
    assert "accepted_at" in body


def test_ingest_run_status_404_for_unknown_id(client):
    r = client.get("/ingest/runs/ing_doesnotexist")
    assert r.status_code == 404


def test_ingest_runs_list_empty(client):
    r = client.get("/ingest/runs")
    assert r.status_code == 200
    assert r.json() == []


# ─── /sync-status ────────────────────────────────────────────────────────────
def test_sync_status_never_synced_when_no_manifest(client):
    r = client.get("/sync-status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "never_synced"
    assert body["n_files"] == 0


def test_sync_status_reads_existing_manifest(client, tmp_path):
    # Seed a manifest at the configured path
    manifest_path = Path(tmp_path / ".klerk" / "drive-manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"file_id_1": "etag1", "file_id_2": "etag2"}))
    r = client.get("/sync-status")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ready"
    assert body["n_files"] == 2


# ─── /actions/extract ────────────────────────────────────────────────────────
def test_actions_extract_validates_one_of(client):
    r = client.post("/actions/extract", json={})
    assert r.status_code == 422  # neither doc_id nor text


def test_actions_extract_accepts_text_input(client, monkeypatch):
    """Step 7 wired the agent; without LLM creds it propagates as a runtime error."""
    from klerk.agent._models import ActionExtraction, ActionItem
    from klerk.agent import action_items

    monkeypatch.setattr(
        action_items,
        "ask_typed",
        lambda *a, **kw: ActionExtraction(
            items=[ActionItem(assignee="Yan", action="Review report", due="Friday")],
            source="text",
        ),
    )
    r = client.post(
        "/actions/extract",
        json={"text": "Yan should review the report by Friday."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["n_items"] == 1
    assert body["items"][0]["assignee"] == "Yan"
    assert body["source"] == "text"


# ─── /draft ──────────────────────────────────────────────────────────────────
def test_draft_validates_topic_required(client):
    r = client.post("/draft", json={})
    assert r.status_code == 422


def test_draft_validates_n_sections_bounds(client):
    r = client.post("/draft", json={"topic": "Q1 budget", "n_sections": 20})
    assert r.status_code == 422


# ─── /drift ──────────────────────────────────────────────────────────────────
def test_drift_recent_empty_when_no_file(client):
    r = client.get("/drift/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["n_events"] == 0


def test_drift_recent_reads_jsonl(client, tmp_path):
    drift_path = Path(tmp_path / ".klerk" / "drift-events.jsonl")
    drift_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "type": "doc_changed",
        "doc_id": "hr_policy_2025",
        "timestamp": "2026-05-29T10:00:00Z",
        "summary": "Parental leave clause re-worded.",
    }
    drift_path.write_text(json.dumps(event) + "\n")
    r = client.get("/drift/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["n_events"] == 1
    assert body["events"][0]["doc_id"] == "hr_policy_2025"


def test_drift_scan_returns_202_with_run_id(client):
    """Step 7 wired the agent; /drift/scan now fires a background scan."""
    r = client.post("/drift/scan")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["run_id"].startswith("drf_")


# ─── OpenAPI surface ─────────────────────────────────────────────────────────
def test_openapi_lists_all_planned_endpoints(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for expected in (
        "/health",
        "/chat",
        "/ingest",
        "/ingest/runs",
        "/ingest/runs/{run_id}",
        "/sync-status",
        "/conflicts/scan",
        "/draft",
        "/actions/extract",
        "/drift/recent",
        "/drift/scan",
    ):
        assert expected in paths, f"missing route in OpenAPI: {expected}"
