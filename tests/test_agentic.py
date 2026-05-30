"""Step-7 agentic capabilities — A (Escalation) / B (Action Items) /
E (Drift). Capability D (Writer) is already exercised by the existing
proposal_pipeline tests; here we just verify the Pydantic façade.

LLM calls are mocked; the drift agent is exercised end to end against a
synthetic LanceDB snapshot since the corpus + manifest tests don't need
the LLM.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klerk.agent._models import (
    ActionExtraction,
    ActionItem,
    DriftEvent,
    DriftScanReport,
    EscalationDraft,
    WriterDraftSummary,
    WriterSection,
)


# ─── Pydantic models — round-trip + validation ───────────────────────────────
def test_escalation_draft_validates_urgency_enum():
    with pytest.raises(Exception):  # pydantic ValidationError
        EscalationDraft(
            to=["x"], cc=[], subject="s", body="b",
            urgency="urgent",  # invalid
            rationale="r", source_question="q", confidence_observed=0.1,
        )


def test_escalation_draft_clamps_confidence():
    with pytest.raises(Exception):
        EscalationDraft(
            to=["x"], cc=[], subject="s", body="b",
            urgency="high", rationale="r",
            source_question="q", confidence_observed=1.5,  # > 1
        )


def test_action_item_defaults():
    item = ActionItem(assignee="Yan", action="Review the doc.")
    assert item.priority == "medium"
    assert item.due is None
    assert item.source_chunk is None


def test_action_extraction_serializes():
    payload = ActionExtraction(
        items=[ActionItem(assignee="Yan", action="Review the doc.")],
        source="text",
    )
    data = json.loads(payload.model_dump_json())
    assert data["source"] == "text"
    assert len(data["items"]) == 1


def test_drift_event_requires_known_type():
    with pytest.raises(Exception):
        DriftEvent(
            type="something_else",  # invalid
            doc_id="d", timestamp=datetime.now(timezone.utc), summary="s",
        )


def test_drift_scan_report_defaults():
    report = DriftScanReport(run_id="drf_x", started_at=datetime.now(timezone.utc))
    assert report.events == []
    assert report.n_docs_scanned == 0
    assert report.error is None


def test_writer_summary_serialises():
    s = WriterDraftSummary(
        topic="Q1 review",
        locale="en",
        sections=[WriterSection(title="Intro", body="...", winner="A", citations=["c1"])],
        rubric_mean=0.82,
        generated_at=datetime.now(timezone.utc),
    )
    data = json.loads(s.model_dump_json())
    assert data["sections"][0]["winner"] == "A"
    assert data["rubric_mean"] == 0.82


# ─── Escalation agent ────────────────────────────────────────────────────────
def test_escalation_draft_routes_through_ask_json(monkeypatch):
    from klerk.agent import escalation

    captured: dict = {}

    def fake_ask_json(schema, *, system, user, locale, max_tokens):
        captured["system"] = system
        captured["user"] = user
        captured["locale"] = locale
        return EscalationDraft(
            to=["hr@fata-organa.com"],
            cc=[],
            subject="Need policy clarification",
            body="...",
            urgency="medium",
            rationale="klerk could not find a grounded answer.",
            source_question="What is the parental leave policy?",
            confidence_observed=0.15,
        )

    monkeypatch.setattr(escalation, "ask_json", fake_ask_json)
    out = escalation.draft(
        question="What is the parental leave policy?",
        confidence=0.15,
        retrieved_excerpt="some retrieved text",
        locale="en",
    )
    assert isinstance(out, EscalationDraft)
    assert "OBSERVED CONFIDENCE: 0.15" in captured["user"]
    assert "USER QUESTION:" in captured["user"]
    assert captured["locale"] == "en"


def test_escalation_omits_retrieved_excerpt_when_empty(monkeypatch):
    from klerk.agent import escalation

    captured: dict = {}
    monkeypatch.setattr(
        escalation,
        "ask_json",
        lambda *a, **kw: (
            captured.update(kw)
            or EscalationDraft(
                to=["info@fata-organa.com"], cc=[],
                subject="Q",
                body="b",
                urgency="low",
                rationale="r",
                source_question="q",
                confidence_observed=0.0,
            )
        ),
    )
    escalation.draft(question="q", confidence=0.0, retrieved_excerpt="")
    assert "WHAT KLERK DID FIND" not in captured["user"]


# ─── Action items agent ──────────────────────────────────────────────────────
def test_action_items_extract_requires_one_input():
    from klerk.agent.action_items import extract

    with pytest.raises(ValueError, match="either"):
        extract()
    with pytest.raises(ValueError, match="not both"):
        extract(doc_id="d", text="t")


def test_action_items_extract_from_text(monkeypatch):
    from klerk.agent import action_items

    def fake_ask_json(schema, *, system, user, locale, max_tokens):
        assert "TEXT:\n" in user
        return ActionExtraction(
            items=[ActionItem(assignee="Tanaka", action="Review report", due="Friday")],
            source="text",
        )

    monkeypatch.setattr(action_items, "ask_json", fake_ask_json)
    result = action_items.extract(text="Tanaka, please review the report by Friday.")
    assert result.source == "text"
    assert len(result.items) == 1
    assert result.items[0].assignee == "Tanaka"


def test_action_items_extract_forces_source_field(monkeypatch):
    """Even if the model fills source wrong, the agent overrides it."""
    from klerk.agent import action_items

    def fake_ask_json(*a, **kw):
        return ActionExtraction(
            items=[ActionItem(assignee="x", action="y")],
            source="wrong",  # the model lied
        )

    monkeypatch.setattr(action_items, "ask_json", fake_ask_json)
    result = action_items.extract(text="hi")
    assert result.source == "text"


# ─── Drift agent ─────────────────────────────────────────────────────────────
@pytest.fixture
def drift_state(tmp_path, monkeypatch):
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("KLERK_DRIFT_THRESHOLD", "0.25")
    yield tmp_path


def _make_lance_corpus(records: list[dict]) -> MagicMock:
    """Build a MagicMock db whose .open_table(...).to_pandas() returns records."""
    import pandas as pd

    table = MagicMock()
    table.to_pandas.return_value = pd.DataFrame(records)
    db = MagicMock()
    db.list_tables.return_value = ["corpus"]
    db.open_table.return_value = table
    return db


def test_drift_emits_doc_added_on_first_run(drift_state, monkeypatch):
    from klerk.agent import drift

    db = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "alpha"},
        {"chunk_id": "d1:1", "doc_id": "d1", "text": "beta"},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db)

    report = drift.scan()
    assert report.error is None
    assert report.n_docs_scanned == 1
    assert len(report.events) == 1
    assert report.events[0].type == "doc_added"
    assert report.events[0].doc_id == "d1"


def test_drift_emits_doc_changed_when_text_diffs(drift_state, monkeypatch):
    from klerk.agent import drift

    # First scan establishes the baseline.
    db1 = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "old text"},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db1)
    drift.scan()

    # Second scan with different text.
    db2 = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "new text"},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db2)
    report = drift.scan()
    assert any(e.type == "doc_changed" and e.doc_id == "d1" for e in report.events)


def test_drift_emits_doc_removed(drift_state, monkeypatch):
    from klerk.agent import drift

    db1 = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "x"},
        {"chunk_id": "d2:0", "doc_id": "d2", "text": "y"},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db1)
    drift.scan()

    db2 = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "x"},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db2)
    report = drift.scan()
    assert any(e.type == "doc_removed" and e.doc_id == "d2" for e in report.events)


def test_drift_no_events_when_unchanged(drift_state, monkeypatch):
    from klerk.agent import drift

    records = [{"chunk_id": "d1:0", "doc_id": "d1", "text": "same"}]
    db = _make_lance_corpus(records)
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db)

    drift.scan()
    second = drift.scan()
    assert second.events == []


def test_drift_handles_empty_corpus(drift_state, monkeypatch):
    from klerk.agent import drift

    db = MagicMock()
    db.list_tables.return_value = []  # no corpus table at all
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db)

    report = drift.scan()
    assert report.error is None
    assert report.events == []


def test_drift_scope_drift_emitted_when_centroid_jumps(drift_state, monkeypatch):
    """Embedding centroid moves > threshold → scope_drift event."""
    from klerk.agent import drift

    # Baseline: centroid at (1, 0, 0)
    db1 = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "first text",
         "vector": [1.0, 0.0, 0.0]},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db1)
    drift.scan()

    # New: centroid at (0, 1, 0) → cosine sim = 0 → distance = 1 >> threshold
    db2 = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "totally different text",
         "vector": [0.0, 1.0, 0.0]},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db2)
    report = drift.scan()
    types = {e.type for e in report.events if e.doc_id == "d1"}
    assert "doc_changed" in types
    assert "scope_drift" in types


def test_drift_writes_events_to_jsonl(drift_state, monkeypatch):
    from klerk.agent import drift

    db = _make_lance_corpus([
        {"chunk_id": "d1:0", "doc_id": "d1", "text": "x"},
    ])
    monkeypatch.setattr("klerk.rag.store.open_db", lambda: db)
    drift.scan()

    jsonl = drift_state / "drift-events.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["type"] == "doc_added"
    assert parsed["doc_id"] == "d1"


# ─── Writer façade ───────────────────────────────────────────────────────────
def test_writer_maps_internal_proposal_to_public_summary(monkeypatch):
    from klerk.agent import writer
    from klerk.agent.proposal_pipeline import Proposal
    from klerk.agent.schemas import (
        Adjudication,
        DraftedSection,
        ProposalScope,
        ProposalSection,
        RubricScores,
    )
    from klerk.agent.proposal_pipeline import SectionRound

    fake_proposal = Proposal(
        topic="Q1 review",
        locale="en",
        scope=ProposalScope(
            sections=[
                ProposalSection(title="Intro", bullets=["b1"], target_chunks=[]),
            ],
        ),
        rounds=[
            SectionRound(
                section=ProposalSection(title="Intro", bullets=["b1"], target_chunks=[]),
                retrieved=[],
                draft_a=DraftedSection(
                    section_title="Intro", drafter_id="A",
                    body="Body A", citations=["c1"],
                ),
                draft_b=DraftedSection(
                    section_title="Intro", drafter_id="B",
                    body="Body B", citations=["c1", "c2"],
                ),
                adjudication=Adjudication(
                    winner="B",
                    reasons=["B is more cohesive", "B has better citation coverage"],
                ),
                rubric=RubricScores(
                    faithfulness=0.9, citation_coverage=0.8,
                    contradiction_freeness=1.0, section_coverage=0.85,
                    tone=0.9, notes=[],
                ),
            ),
        ],
        summary_rubric=RubricScores(
            faithfulness=0.9, citation_coverage=0.8,
            contradiction_freeness=1.0, section_coverage=0.85,
            tone=0.9, notes=[],
        ),
    )
    monkeypatch.setattr(writer, "propose", lambda *a, **kw: fake_proposal)
    summary = writer.write_draft("Q1 review")
    assert summary.topic == "Q1 review"
    assert summary.sections[0].winner == "B"
    assert summary.sections[0].body == "Body B"
    assert summary.rubric_mean is not None
