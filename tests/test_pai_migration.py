"""PydanticAI migration (cluster 3): action_items, kg_extract,
contradiction.judge_pair now route through klerk.agent.pai.ask_typed.

`ask_typed` itself is exercised with a stubbed pydantic_ai.Agent so no
network/creds are needed; the three call-sites are checked for the swap +
their post-processing (source pinning, evidence merge, entity stamping).
"""

from __future__ import annotations

import pytest

from klerk.agent import contradiction, kg_extract, pai
from klerk.agent._models import ActionExtraction, ActionItem
from klerk.agent.contradiction import ConflictGroup
from klerk.agent.schemas import ContradictionFinding, Entity, ExtractedGraph, Relation


# ─── ask_typed bridge ────────────────────────────────────────────────────────
class _FakeResult:
    def __init__(self, output):
        self.output = output


class _FakeAgent:
    """Stand-in for pydantic_ai.Agent: records construction, returns canned output."""

    last_kwargs: dict = {}
    canned = None

    def __init__(self, model, *, output_type, system_prompt, retries, model_settings):
        _FakeAgent.last_kwargs = {
            "model": model,
            "output_type": output_type,
            "system_prompt": system_prompt,
            "retries": retries,
            "model_settings": model_settings,
        }
        self._output_type = output_type

    def run_sync(self, user_prompt):
        return _FakeResult(_FakeAgent.canned)


@pytest.fixture
def stub_pai(monkeypatch):
    """Patch ask_typed's Agent + model builder so no proxy is touched."""
    monkeypatch.setattr(pai, "_model_for", lambda locale: f"model::{locale}")

    import pydantic_ai

    monkeypatch.setattr(pydantic_ai, "Agent", _FakeAgent)
    return _FakeAgent


def test_ask_typed_builds_agent_and_returns_output(stub_pai):
    expected = ActionExtraction(items=[], source="text")
    stub_pai.canned = expected
    out = pai.ask_typed(
        ActionExtraction, system="sys", user="usr", locale="id",
        temperature=0.0, max_tokens=512,
    )
    assert out is expected
    kw = stub_pai.last_kwargs
    assert kw["output_type"] is ActionExtraction
    assert kw["system_prompt"] == "sys"
    assert kw["model"] == "model::id"  # locale propagated into model selection
    assert kw["model_settings"]["max_tokens"] == 512


def test_ask_typed_omits_max_tokens_when_none(stub_pai):
    stub_pai.canned = ActionExtraction(items=[], source="text")
    pai.ask_typed(ActionExtraction, system="s", user="u", max_tokens=None)
    assert "max_tokens" not in stub_pai.last_kwargs["model_settings"]


# ─── action_items uses ask_typed ─────────────────────────────────────────────
def test_action_items_calls_ask_typed(monkeypatch):
    from klerk.agent import action_items

    calls = {}

    def fake(schema, *, system, user, locale, max_tokens):
        calls["schema"] = schema
        return ActionExtraction(
            items=[ActionItem(assignee="A", action="do")], source="ignored"
        )

    monkeypatch.setattr(action_items, "ask_typed", fake)
    out = action_items.extract(text="something")
    assert calls["schema"] is ActionExtraction
    assert out.source == "text"  # pinned by caller, model's value discarded


# ─── kg_extract uses ask_typed ───────────────────────────────────────────────
def test_kg_extract_chunk_calls_ask_typed(monkeypatch):
    canned = ExtractedGraph(
        entities=[Entity(id="e1", type="organization", name="CAC", aliases=[])],
        relations=[Relation(source="e1", target="e1", verb="is", evidence_chunk="")],
    )

    def fake(schema, *, system, user, locale, max_tokens):
        assert schema is ExtractedGraph
        assert "CHUNK_ID: c1" in user
        return canned

    monkeypatch.setattr(kg_extract, "ask_typed", fake)
    out = kg_extract.extract_chunk("c1", "CAC Holding is a company.", locale="en")
    assert out is canned


# ─── contradiction.judge_pair uses ask_typed ─────────────────────────────────
def test_judge_pair_stamps_entity_and_returns_finding(monkeypatch):
    def fake(schema, *, system, user, locale, max_tokens):
        return ContradictionFinding(
            consistent=False, contradiction="2023 vs 2025",
            involved_chunks=["c1", "c2"],
        )

    monkeypatch.setattr(contradiction, "ask_typed", fake)
    grp = ConflictGroup(source="policy", target="14 days", verb_stem="cap", evidence_chunks=["c1", "c2"])
    finding = contradiction.judge_pair(grp, {"c1": "14 days", "c2": "30 days"}, locale="en")
    assert finding.consistent is False
    assert finding.entity_or_relation == "policy →[cap]→ 14 days"


def test_judge_pair_survives_llm_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("proxy down")

    monkeypatch.setattr(contradiction, "ask_typed", boom)
    grp = ConflictGroup(source="s", target="t", verb_stem="v", evidence_chunks=["c1", "c2"])
    finding = contradiction.judge_pair(grp, {}, locale="en")
    # error becomes a flagged, non-fatal finding
    assert finding.consistent is True
    assert "proxy down" in finding.contradiction
    assert finding.entity_or_relation == "s →[v]→ t"
