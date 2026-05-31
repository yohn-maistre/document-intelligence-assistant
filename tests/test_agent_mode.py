"""Midday `--agent` / `--json` dual-mode contract (Phase A.1, session S1).

For representative verbs we assert the external-tool contract:

  * ``--agent`` writes EXACTLY ONE ``json.loads``-parseable object to stdout,
  * exit code 0 on success,
  * NO ANSI escape sequences on stdout (human Rich text goes to stderr),
  * error cases exit non-zero (and still emit a JSON object on stdout).

All LLM / network calls are monkeypatched — nothing here touches the proxy.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from klerk.agent._models import (
    ActionExtraction,
    ActionItem,
    EscalationDraft,
)
from klerk.cli.main import app

runner = CliRunner()

ESC = "\x1b"  # ANSI escape introducer


def _assert_single_json_stdout(result, *, expect_exit: int = 0) -> dict:
    """Stdout is exactly one JSON object, no ANSI, expected exit code."""
    assert result.exit_code == expect_exit, (
        f"exit={result.exit_code} stdout={result.stdout!r}"
    )
    out = result.stdout
    assert ESC not in out, f"ANSI leaked onto stdout: {out!r}"
    # Exactly one JSON value: json.loads consumes the whole (single-line) body.
    obj = json.loads(out)
    assert isinstance(obj, (dict, list))
    # And there is only one line of actual JSON payload.
    assert out.strip().count("\n") == 0
    return obj


# ─── search verbs ────────────────────────────────────────────────────────────
@pytest.fixture
def stub_search(monkeypatch):
    import klerk.cli.search_cmd as sc

    hits = [
        {"chunk_id": "d1:0", "doc_id": "d1", "locale": "en", "text": "alpha beta"},
        {"chunk_id": "d2:1", "doc_id": "d2", "locale": "en", "text": "gamma"},
    ]
    monkeypatch.setattr(sc, "search_bm25", lambda q, k=8: hits)
    monkeypatch.setattr(sc, "search_vector", lambda qv, k=8: hits)
    monkeypatch.setattr(sc, "embed_query", lambda q: [0.0, 0.1])

    class _R:
        def __init__(self, cid):
            self.chunk_id = cid
            self.doc_id = "d1"
            self.score = 0.9
            self.vector_rank = 1
            self.bm25_rank = 2
            self.locale = "en"
            self.text = "alpha beta gamma"

    monkeypatch.setattr(sc, "search_hybrid", lambda q, **kw: [_R("d1:0"), _R("d2:1")])
    return sc


@pytest.mark.parametrize("sub", ["bm25", "vector", "hybrid"])
def test_search_agent_mode(stub_search, sub):
    result = runner.invoke(app, ["search", sub, "my query", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["mode"] == sub
    assert obj["query"] == "my query"


def test_search_human_mode_unbroken(stub_search):
    """Without --agent, the Rich table still renders (no JSON contract)."""
    result = runner.invoke(app, ["search", "bm25", "q"])
    assert result.exit_code == 0
    # Human output present, and it's NOT a bare JSON object.
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_json_alias_equivalent(stub_search):
    result = runner.invoke(app, ["search", "bm25", "q", "--json"])
    obj = _assert_single_json_stdout(result)
    assert obj["mode"] == "bm25"


# ─── ask (CRAG) ──────────────────────────────────────────────────────────────
def test_ask_agent_mode(monkeypatch):
    import klerk.cli.ask_cmd as ac

    class _Ans:
        answer = "42"
        confidence = 0.88
        locale = "en"
        citations = ["d1:0"]

    class _Trace:
        sub_questions = ["q1"]
        judgments = []
        corrections = []
        retrievals = []
        answer = _Ans()

    monkeypatch.setattr(ac, "crag_ask", lambda *a, **k: _Trace())
    result = runner.invoke(app, ["ask", "what is the answer", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["answer"] == "42"
    assert obj["citations"] == ["d1:0"]


# ─── extract-actions (Brief Option B) ────────────────────────────────────────
def test_extract_actions_agent_mode(monkeypatch):
    import klerk.cli.extract_actions_cmd as ea

    def fake_extract(*, doc_id, text, locale):
        return ActionExtraction(
            items=[ActionItem(assignee="Budi", action="ship docs", priority="high")],
            source="text",
        )

    monkeypatch.setattr(ea, "extract", fake_extract)
    result = runner.invoke(app, ["extract-actions", "--text", "Budi to ship docs", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["source"] == "text"
    assert obj["items"][0]["assignee"] == "Budi"


def test_extract_actions_requires_input():
    """No --text and no --doc-id → non-zero exit, JSON error object on stdout."""
    result = runner.invoke(app, ["extract-actions", "--agent"])
    obj = _assert_single_json_stdout(result, expect_exit=1)
    assert "error" in obj


def test_extract_actions_llm_error(monkeypatch):
    import klerk.cli.extract_actions_cmd as ea

    def boom(**kw):
        raise RuntimeError("corpus empty")

    monkeypatch.setattr(ea, "extract", boom)
    result = runner.invoke(app, ["extract-actions", "--text", "x", "--agent"])
    obj = _assert_single_json_stdout(result, expect_exit=1)
    assert "error" in obj


# ─── escalate draft (Brief Option A) ─────────────────────────────────────────
def test_escalate_draft_agent_mode(monkeypatch):
    import klerk.cli.escalate_cmd as ec

    def fake_draft(*, question, confidence, retrieved_excerpt, locale):
        return EscalationDraft(
            to=["hr@fata-organa.com"],
            cc=[],
            subject="Need help",
            body="Please advise.",
            urgency="medium",
            rationale="low confidence",
            source_question=question,
            confidence_observed=confidence,
        )

    monkeypatch.setattr(ec, "draft", fake_draft)
    result = runner.invoke(app, ["escalate", "draft", "how much leave?", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["to"] == ["hr@fata-organa.com"]
    assert obj["subject"] == "Need help"
    assert obj["source_question"] == "how much leave?"


def test_escalate_draft_error(monkeypatch):
    import klerk.cli.escalate_cmd as ec

    def boom(**kw):
        raise RuntimeError("proxy down")

    monkeypatch.setattr(ec, "draft", boom)
    result = runner.invoke(app, ["escalate", "draft", "q", "--agent"])
    obj = _assert_single_json_stdout(result, expect_exit=1)
    assert "error" in obj


# ─── contradict scan (Brief Option C core) ───────────────────────────────────
def test_contradict_scan_agent_empty(monkeypatch):
    import klerk.cli.contradict_cmd as cc

    monkeypatch.setattr(cc, "scan", lambda *, locale="en": [])
    monkeypatch.setattr(cc, "save_report", lambda findings: "/tmp/report.md")
    result = runner.invoke(app, ["contradict", "scan", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["n_findings"] == 0


def test_contradict_scan_error(monkeypatch):
    import klerk.cli.contradict_cmd as cc

    def boom(*, locale="en"):
        raise RuntimeError("KG empty")

    monkeypatch.setattr(cc, "scan", boom)
    result = runner.invoke(app, ["contradict", "scan", "--agent"])
    obj = _assert_single_json_stdout(result, expect_exit=1)
    assert "error" in obj


# ─── kg stats ────────────────────────────────────────────────────────────────
def test_kg_stats_agent_mode(monkeypatch):
    import klerk.cli.kg_cmd as kc

    class _S:
        n_entities = 5
        n_relations = 7
        n_chunks_seen = 12

    monkeypatch.setattr(kc.kg_extract, "stats", lambda: _S())
    result = runner.invoke(app, ["kg", "stats", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["entities"] == 5
    assert obj["empty"] is False


def test_kg_stats_empty_agent_mode(monkeypatch):
    import klerk.cli.kg_cmd as kc

    class _S:
        n_entities = 0
        n_relations = 0
        n_chunks_seen = 0

    monkeypatch.setattr(kc.kg_extract, "stats", lambda: _S())
    result = runner.invoke(app, ["kg", "stats", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["empty"] is True


# ─── index stats ─────────────────────────────────────────────────────────────
def test_index_stats_agent_mode(monkeypatch):
    import klerk.cli.index_cmd as ic

    class _S:
        table = "corpus_v1"
        n_rows = 100
        embed_dim = 1024
        fts_indexed = True

    monkeypatch.setattr(ic, "stats", lambda: _S())
    result = runner.invoke(app, ["index", "stats", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["rows"] == 100
    assert obj["fts_indexed"] is True


def test_index_stats_empty_agent_mode(monkeypatch):
    import klerk.cli.index_cmd as ic

    monkeypatch.setattr(ic, "stats", lambda: None)
    result = runner.invoke(app, ["index", "stats", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["rows"] == 0


# ─── drive status ────────────────────────────────────────────────────────────
def test_drive_status_agent_mode(monkeypatch):
    import klerk.drive.sync as ds

    monkeypatch.setattr(ds, "load_manifest", lambda: {"a": 1, "b": 2})
    monkeypatch.setattr(ds, "load_page_token", lambda: "tok123")
    monkeypatch.setattr(ds, "manifest_path", lambda: "/tmp/manifest.json")
    monkeypatch.setattr(ds, "page_token_path", lambda: "/tmp/token")
    result = runner.invoke(app, ["drive", "status", "--agent"])
    obj = _assert_single_json_stdout(result)
    assert obj["manifest_files"] == 2
    assert obj["page_token_seeded"] is True
