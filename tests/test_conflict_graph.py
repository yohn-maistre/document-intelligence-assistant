"""LangGraph Conflict Reporter spine + agentskills.io manifests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import networkx as nx
import pytest

from klerk.agent.skills import list_manifests, manifests


# ─── agentskills.io manifests ────────────────────────────────────────────────
def test_five_manifests_shipped():
    paths = list_manifests()
    names = {p.stem for p in paths}
    assert names == {
        "escalation",
        "action_items",
        "conflict_report",
        "draft_doc",
        "drift",
    }


def test_every_manifest_has_required_top_level_keys():
    for m in manifests():
        assert m["apiVersion"] == "skills.dev/v1"
        assert m["kind"] == "Skill"
        assert "metadata" in m
        assert "spec" in m
        assert m["metadata"]["name"].startswith("klerk.")
        assert m["metadata"]["version"]


def test_every_manifest_declares_runtime():
    for m in manifests():
        spec = m["spec"]
        assert "runtime" in spec
        py = spec["runtime"]["python"]
        assert py["module"].startswith("klerk.")
        assert py["callable"]


def test_writer_manifest_describes_pipeline_stages():
    writer = next(m for m in manifests() if m["metadata"]["name"] == "klerk.draft_doc")
    assert "pipeline" in writer["spec"]
    stages = writer["spec"]["pipeline"]["stages"]
    assert "drafter_a" in stages
    assert "drafter_b" in stages
    assert "adjudicator" in stages


def test_conflict_manifest_declares_langgraph_nodes():
    cr = next(m for m in manifests() if m["metadata"]["name"] == "klerk.conflict_reporter")
    nodes = cr["spec"]["orchestration"]["graph"]["nodes"]
    assert nodes == ["retrieve_docs", "pair_facts", "judge_conflict", "format_report"]


def test_drift_manifest_declares_schedule():
    drift = next(m for m in manifests() if m["metadata"]["name"] == "klerk.drift_detector")
    triggers = drift["spec"]["triggers"]
    schedules = [t for t in triggers if "schedule" in t]
    assert schedules
    assert schedules[0]["schedule"]["cron"] == "0 2 * * *"


# ─── LangGraph spine: each node tested in isolation ──────────────────────────
@pytest.fixture
def fake_kg(monkeypatch):
    """Build a tiny KG with one (source, verb, target) triple repeated
    across two evidence chunks — a candidate for the contradiction sweep."""
    g = nx.MultiDiGraph()
    g.add_node("Q1 leave policy")
    g.add_node("12 weeks")
    g.add_edge(
        "Q1 leave policy",
        "12 weeks",
        verb="grants",
        evidence_chunk="hr_parental_leave_2023:0",
    )
    g.add_edge(
        "Q1 leave policy",
        "12 weeks",
        verb="grants",
        evidence_chunk="hr_parental_leave_2025:0",
    )
    monkeypatch.setattr("klerk.orchestrate.conflict_graph.load_graph", lambda: g)
    monkeypatch.setattr(
        "klerk.orchestrate.conflict_graph._chunk_text_index",
        lambda: {
            "hr_parental_leave_2023:0": "Primary caregiver gets 12 weeks (2023).",
            "hr_parental_leave_2025:0": "Primary caregiver gets 16 weeks (2025).",
        },
    )
    yield


def test_retrieve_docs_loads_kg_and_groups(fake_kg):
    from klerk.orchestrate.conflict_graph import _retrieve_docs

    state = _retrieve_docs({"locale": "en"})
    assert "chunk_text" in state
    assert "candidate_groups" in state
    assert len(state["candidate_groups"]) == 1
    grp = state["candidate_groups"][0]
    assert grp["source"] == "Q1 leave policy"
    assert grp["target"] == "12 weeks"
    assert sorted(grp["evidence_chunks"]) == [
        "hr_parental_leave_2023:0",
        "hr_parental_leave_2025:0",
    ]


def test_retrieve_docs_raises_on_empty_kg(monkeypatch):
    from klerk.orchestrate.conflict_graph import _retrieve_docs

    monkeypatch.setattr(
        "klerk.orchestrate.conflict_graph.load_graph",
        lambda: nx.MultiDiGraph(),
    )
    with pytest.raises(RuntimeError, match="no KG"):
        _retrieve_docs({"locale": "en"})


def test_pair_facts_renders_prompts():
    from klerk.orchestrate.conflict_graph import _pair_facts

    state = _pair_facts({
        "chunk_text": {
            "c1": "Twelve weeks paid leave.",
            "c2": "Sixteen weeks paid leave.",
        },
        "candidate_groups": [{
            "source": "leave_policy",
            "target": "duration",
            "verb_stem": "grant",
            "evidence_chunks": ["c1", "c2"],
        }],
    })
    assert len(state["paired_prompts"]) == 1
    prompt = state["paired_prompts"][0]
    assert prompt["entity_or_relation"] == "leave_policy →[grant]→ duration"
    assert "Twelve weeks paid leave." in prompt["user_prompt"]
    assert "Sixteen weeks paid leave." in prompt["user_prompt"]


def test_judge_conflict_calls_llm_per_pair(monkeypatch):
    from klerk.agent.schemas import ContradictionFinding
    from klerk.orchestrate.conflict_graph import _judge_conflict

    calls = []

    def fake_ask_json(schema, *, system, user, locale, max_tokens):
        calls.append(user)
        return ContradictionFinding(
            consistent=False,
            contradiction="Two different durations across docs.",
            involved_chunks=["c1", "c2"],
            entity_or_relation="placeholder (will be stamped by graph)",
        )

    monkeypatch.setattr("klerk.orchestrate.conflict_graph.ask_json", fake_ask_json)
    state = _judge_conflict({
        "locale": "en",
        "paired_prompts": [
            {
                "entity_or_relation": "leave_policy →[grant]→ duration",
                "evidence_chunks": ["c1", "c2"],
                "user_prompt": "...prompt body...",
            },
        ],
    })
    assert len(calls) == 1
    assert len(state["findings"]) == 1
    finding = state["findings"][0]
    assert finding["consistent"] is False
    assert finding["entity_or_relation"] == "leave_policy →[grant]→ duration"


def test_judge_conflict_survives_per_pair_failure(monkeypatch):
    from klerk.orchestrate.conflict_graph import _judge_conflict

    def boom(*a, **kw):
        raise RuntimeError("LLM timeout")

    monkeypatch.setattr("klerk.orchestrate.conflict_graph.ask_json", boom)
    state = _judge_conflict({
        "locale": "en",
        "paired_prompts": [{
            "entity_or_relation": "x →[verb]→ y",
            "evidence_chunks": ["c1"],
            "user_prompt": "...",
        }],
    })
    assert len(state["findings"]) == 1
    assert "judge error" in state["findings"][0]["contradiction"]


def test_format_report_builds_markdown():
    from klerk.orchestrate.conflict_graph import _format_report

    state = _format_report({
        "findings": [{
            "entity_or_relation": "leave_policy →[grant]→ duration",
            "consistent": False,
            "contradiction": "12wk in 2023 vs 16wk in 2025.",
            "evidence_chunks": ["c1", "c2"],
        }],
    })
    assert "Contradiction report" in state["report_markdown"]
    assert "leave_policy" in state["report_markdown"]
    assert state["n_findings"] == 1


# ─── End-to-end via compiled graph ───────────────────────────────────────────
def test_graph_runs_end_to_end(fake_kg, monkeypatch):
    """The full StateGraph from retrieve_docs through format_report."""
    from klerk.agent.schemas import ContradictionFinding
    from klerk.orchestrate.conflict_graph import run

    def fake_ask_json(schema, *, system, user, locale, max_tokens):
        return ContradictionFinding(
            consistent=False,
            contradiction="Different durations.",
            involved_chunks=["hr_parental_leave_2023:0", "hr_parental_leave_2025:0"],
            entity_or_relation="placeholder",
        )

    monkeypatch.setattr("klerk.orchestrate.conflict_graph.ask_json", fake_ask_json)
    # Reset the compiled-graph cache so the test exercises a fresh build
    monkeypatch.setattr("klerk.orchestrate.conflict_graph._compiled_graph", None)

    state = run(locale="en")
    assert state["n_findings"] == 1
    assert "Contradiction report" in state["report_markdown"]
    assert state["locale"] == "en"


def test_graph_exports_mermaid_diagram(tmp_path):
    from klerk.orchestrate.conflict_graph import export_diagram

    path = export_diagram(tmp_path / "out.mmd")
    text = path.read_text()
    # Either real Mermaid syntax from langgraph, or the fallback shipped
    # in conflict_graph.py — both contain the four node names.
    for node in ("retrieve_docs", "pair_facts", "judge_conflict", "format_report"):
        assert node in text
