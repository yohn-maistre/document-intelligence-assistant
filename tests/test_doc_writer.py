"""doc_writer LangGraph spine (capability D).

The LLM-bound stage functions (plan_scope / _draft_section / adjudicate /
score_rubric) and retrieval (gather_evidence) are monkeypatched so the graph
runs fully offline. We verify:

  - the graph runs scope → A‖B → tracer → adjudicator → critic and assembles
    a Proposal with one round per scoped section
  - both drafters actually run (disjoint draft_a / draft_b state keys)
  - the winning draft + citation-check matrix track the adjudication
  - durable checkpoint save/load round-trips; resume returns the cached doc
    without re-running the graph
  - propose() delegates to the graph
"""

from __future__ import annotations

import pytest

from klerk.agent import doc_writer as dw
from klerk.agent import doc_writer_graph as dwg
from klerk.agent.schemas import (
    Adjudication,
    DraftedSection,
    ProposalScope,
    ProposalSection,
    RubricScores,
)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path / ".klerk"))
    # Reset the cached compiled graph so each test builds fresh.
    dwg._compiled_graph = None
    yield
    dwg._compiled_graph = None


@pytest.fixture
def stub_stages(monkeypatch):
    """Patch every LLM/retrieval-bound stage with deterministic fakes."""
    sections = [
        ProposalSection(title="Intro", bullets=["b1"], target_chunks=[]),
        ProposalSection(title="Body", bullets=["b2"], target_chunks=[]),
    ]
    scope = ProposalScope(sections=sections)

    monkeypatch.setattr(dw, "plan_scope", lambda *a, **k: scope)
    monkeypatch.setattr(dw, "gather_evidence", lambda section, **k: [])

    def fake_draft(section, chunks, *, drafter_id, locale):
        return DraftedSection(
            section_title=section.title,
            drafter_id=drafter_id,
            body=f"{drafter_id} draft of {section.title}",
            citations=[f"{drafter_id.lower()}1"],
        )

    monkeypatch.setattr(dw, "_draft_section", fake_draft)
    # B always wins so we can assert the winner-tracking deterministically.
    monkeypatch.setattr(
        dw, "adjudicate",
        lambda section, a, b, **k: Adjudication(winner="B", reasons=["b stronger", "more cited"]),
    )
    monkeypatch.setattr(
        dw, "score_rubric",
        lambda *a, **k: RubricScores(
            faithfulness=0.9, citation_coverage=0.8, contradiction_freeness=1.0,
            section_coverage=0.85, tone=0.9, notes=[],
        ),
    )
    return scope


def test_graph_runs_and_assembles_proposal(stub_stages):
    proposal = dwg.run("Q1 review", run_id="run-1")
    assert proposal.topic == "Q1 review"
    assert len(proposal.rounds) == 2
    # Both drafters ran → both bodies present
    for rnd in proposal.rounds:
        assert rnd.draft_a.body.startswith("A draft")
        assert rnd.draft_b.body.startswith("B draft")
        # B wins per the stubbed adjudication
        assert rnd.adjudication.winner == "B"
        assert rnd.winning_draft.body.startswith("B draft")
    assert proposal.summary_rubric is not None
    assert proposal.summary_rubric.mean == pytest.approx(0.89, abs=0.02)


def test_markdown_uses_winning_drafts(stub_stages):
    proposal = dwg.run("Topic", run_id="run-md")
    md = proposal.to_markdown()
    assert "## Intro" in md and "## Body" in md
    assert "B draft of Intro" in md
    assert "A draft of Intro" not in md  # only the winner is rendered


def test_checkpoint_roundtrip_and_resume(stub_stages, monkeypatch):
    first = dwg.run("Resumable", run_id="run-fixed")
    # A resume must NOT re-invoke the graph — sabotage _build_graph to prove it.
    monkeypatch.setattr(
        dwg, "_build_graph",
        lambda: (_ for _ in ()).throw(AssertionError("graph should not run on resume")),
    )
    resumed = dwg.run("Resumable", run_id="run-fixed", resume=True)
    assert resumed.topic == first.topic == "Resumable"
    assert resumed.to_markdown() == first.to_markdown()


def test_resume_unknown_run_id_falls_through(stub_stages):
    # Unknown id + resume → no cached doc → fresh run (no crash).
    proposal = dwg.run("Fresh", run_id="never-seen", resume=True)
    assert proposal.topic == "Fresh"
    assert len(proposal.rounds) == 2


def test_load_checkpoint_absent_returns_none():
    assert dwg.load_checkpoint("does-not-exist") is None


def test_propose_delegates_to_graph(stub_stages, monkeypatch):
    captured = {}

    def fake_run(topic, **kwargs):
        captured["topic"] = topic
        captured.update(kwargs)
        return "SENTINEL"

    monkeypatch.setattr(dwg, "run", fake_run)
    out = dw.propose("Deleg", n_sections=2, k_per_section=4, locale="id", run_id="r", resume=False)
    assert out == "SENTINEL"
    assert captured["topic"] == "Deleg"
    assert captured["n_sections"] == 2
    assert captured["locale"] == "id"


def test_export_diagram_writes_file(stub_stages, tmp_path):
    out = dwg.export_diagram(tmp_path / "g.mmd")
    assert out.exists()
    assert out.read_text().strip()
