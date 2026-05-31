"""Hermes memory trio — SOUL.md + MEMORY.md + LanceDB `memory_v1`.

All offline: the mock embed backend (`KLERK_EMBED_BACKEND=mock`) drives the
save→recall roundtrip with no model weights, and the PydanticAI extractor is
exercised with a stubbed `ask_typed` so no proxy/creds are touched.
"""

from __future__ import annotations

import pytest

from klerk.memory import MemoryFact, MemoryStore
from klerk.memory.store import SEED_SOUL


@pytest.fixture(autouse=True)
def _mock_embed(monkeypatch):
    monkeypatch.setenv("KLERK_EMBED_BACKEND", "mock")
    yield


@pytest.fixture
def store(tmp_path):
    return MemoryStore(base_dir=tmp_path / "memory")


# ─── SOUL ────────────────────────────────────────────────────────────────────
def test_read_soul_seeds_and_returns_persona(store):
    assert not store.soul_path.exists()
    soul = store.read_soul()
    assert soul == SEED_SOUL
    assert store.soul_path.exists()
    # Persona markers from the brief.
    assert "klerk" in soul
    assert "Bahasa" in soul
    assert "I don't know" in soul


def test_read_soul_is_verbatim_after_edit(store):
    store.read_soul()  # seed
    store.write_soul("# custom soul\nhello")
    assert store.read_soul() == "# custom soul\nhello"


# ─── MEMORY.md append ─────────────────────────────────────────────────────────
def test_memory_md_appends(store):
    store.save("The operator prefers answers in Bahasa Indonesia.")
    store.save(MemoryFact(fact="Project Sakura ships in Q3.", kind="decision"))
    log = store.memory_path.read_text(encoding="utf-8")
    lines = [ln for ln in log.splitlines() if ln.startswith("- [")]
    assert len(lines) == 2
    assert "Bahasa Indonesia" in lines[0]
    assert "(decision)" in lines[1]
    assert "Project Sakura" in lines[1]


# ─── save → recall roundtrip ──────────────────────────────────────────────────
def test_save_then_recall_finds_fact(store):
    store.save("Fata Organa headquarters is in Jakarta.")
    store.save("The quarterly review is held every March.")

    hits = store.recall("Where is the Fata Organa headquarters located?", k=4)
    assert hits, "recall returned no facts"
    texts = [h.fact for h in hits]
    assert any("Jakarta" in t for t in texts)
    top = hits[0]
    assert top.score > 0.0


def test_recall_empty_store_returns_empty(store):
    assert store.recall("anything", k=4) == []


def test_recall_respects_k(store):
    for i in range(6):
        store.save(f"Fact number {i} about the corpus.")
    hits = store.recall("corpus fact", k=2)
    assert len(hits) <= 2


# ─── PydanticAI extraction (stubbed LLM) ──────────────────────────────────────
def test_extract_facts_uses_ask_typed(monkeypatch):
    from klerk.memory import store as store_mod

    captured = {}

    def fake_ask_typed(schema, *, system, user, locale="en", **kw):
        captured["schema"] = schema
        captured["user"] = user
        return schema(
            facts=[
                MemoryFact(fact="Operator prefers Bahasa.", kind="preference"),
                MemoryFact(fact="Sakura ships Q3.", kind="decision"),
            ]
        )

    monkeypatch.setattr("klerk.agent.pai.ask_typed", fake_ask_typed)
    facts = store_mod.extract_facts("klerk replied in Bahasa about Sakura's Q3 ship date.")
    assert len(facts) == 2
    assert facts[0].kind == "preference"
    assert "ASSISTANT TURN" in captured["user"]


def test_extract_facts_caps_at_three(monkeypatch):
    from klerk.memory import store as store_mod

    def fake_ask_typed(schema, *, system, user, locale="en", **kw):
        return schema(facts=[MemoryFact(fact=f"f{i}") for i in range(3)])

    monkeypatch.setattr("klerk.agent.pai.ask_typed", fake_ask_typed)
    facts = store_mod.extract_facts("turn")
    assert len(facts) <= 3


# ─── orchestrator memory prefix (the orchestrator patch is ours) ──────────────
def test_memory_prefix_includes_soul_and_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("KLERK_MEMORY_DIR", str(tmp_path / "mem"))
    from klerk.agent import orchestrator

    MemoryStore().save("Fata Organa headquarters is in Jakarta.")
    prefix = orchestrator._memory_prefix("Where is HQ?")
    assert "IDENTITY (SOUL)" in prefix
    assert "klerk" in prefix
    assert "RECALLED MEMORY" in prefix
    assert "Jakarta" in prefix


def test_memory_prefix_noop_on_failure(monkeypatch):
    from klerk.agent import orchestrator

    def boom():
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr("klerk.memory.MemoryStore", lambda *a, **k: boom())
    # Must never raise; returns empty string so the chat turn proceeds.
    assert orchestrator._memory_prefix("q") == ""
