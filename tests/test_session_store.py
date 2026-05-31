"""SessionStore + sliding-window compaction (cluster 4.1).

JSONL persistence, recent-session listing, and the compaction trigger are
tested with an injected summariser so no LLM is needed.
"""

from __future__ import annotations

import pytest

from klerk.api.session import SessionStore


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path / ".klerk"))
    yield


def _exchange(store, sid, q, a):
    store.append(sid, "user", q)
    store.append(sid, "assistant", a)


def test_append_and_load_roundtrip():
    store = SessionStore()
    _exchange(store, "s1", "hello", "hi there")
    turns = store.load("s1")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].content == "hello"
    assert turns[1].content == "hi there"
    assert turns[0].ts > 0


def test_load_missing_session_is_empty():
    assert SessionStore().load("nope") == []


def test_exists():
    store = SessionStore()
    assert not store.exists("s1")
    store.append("s1", "user", "x")
    assert store.exists("s1")


def test_no_compaction_under_window():
    store = SessionStore(keep_verbatim=3)
    _exchange(store, "s", "q1", "a1")
    _exchange(store, "s", "q2", "a2")  # 2 exchanges ≤ keep_verbatim
    history = store.build_prompt_history("s", summariser=lambda t: "SUMMARY")
    # No summary system message — all verbatim
    assert all(m["role"] in ("user", "assistant") for m in history)
    assert len(history) == 4


def test_compaction_triggers_and_summarises_older_turns():
    store = SessionStore(keep_verbatim=2)
    seen = {}

    def summariser(transcript):
        seen["transcript"] = transcript
        return "OLD CONTEXT SUMMARY"

    for i in range(5):  # 5 exchanges = 10 turns; keep 2 → summarise 6 oldest
        _exchange(store, "s", f"q{i}", f"a{i}")

    history = store.build_prompt_history("s", summariser=summariser)
    assert history[0]["role"] == "system"
    assert "OLD CONTEXT SUMMARY" in history[0]["content"]
    # the 2 most-recent exchanges (4 turns) are kept verbatim
    assert [m["content"] for m in history[1:]] == ["q3", "a3", "q4", "a4"]
    # older turns went into the summariser, recent ones did not
    assert "q0" in seen["transcript"] and "q4" not in seen["transcript"]


def test_summary_cache_hit_skips_resummarise():
    store = SessionStore(keep_verbatim=2)
    calls = {"n": 0}

    def summariser(_t):
        calls["n"] += 1
        return "S"

    for i in range(5):
        _exchange(store, "s", f"q{i}", f"a{i}")

    store.build_prompt_history("s", summariser=summariser)
    store.build_prompt_history("s", summariser=summariser)
    # Same session, same aged-out turn count → cached
    assert calls["n"] == 1


def test_summary_cache_misses_when_more_turns_age_out():
    store = SessionStore(keep_verbatim=2)
    calls = {"n": 0}

    def summariser(_t):
        calls["n"] += 1
        return "S"

    for i in range(5):
        _exchange(store, "s", f"q{i}", f"a{i}")
    store.build_prompt_history("s", summariser=summariser)

    # Add another exchange → one more exchange ages out → cache key changes
    _exchange(store, "s", "q5", "a5")
    store.build_prompt_history("s", summariser=summariser)
    assert calls["n"] == 2


def test_recent_sessions_orders_by_mtime():
    store = SessionStore()
    store.append("alpha", "user", "x")
    store.append("beta", "user", "y")
    recent = store.recent_sessions(limit=5)
    assert set(recent) == {"alpha", "beta"}
    # beta written last → first
    assert recent[0] == "beta"


def test_path_traversal_is_neutralised():
    store = SessionStore()
    store.append("../evil", "user", "x")
    # stored under a sanitised name, still loadable by the same id
    assert store.load("../evil")[0].content == "x"


def test_nemotron_summary_degrades_on_error(monkeypatch):
    store = SessionStore(keep_verbatim=1)
    for i in range(4):
        _exchange(store, "s", f"question number {i}", f"answer number {i}")

    # No summariser → default path; force the LLM import/call to fail.
    import klerk.llm.router as router

    def boom(**_kw):
        raise RuntimeError("proxy down")

    monkeypatch.setattr(router, "complete", boom)
    history = store.build_prompt_history("s")
    # degraded to a truncated transcript, but still produced a summary message
    assert history[0]["role"] == "system"
    assert history[0]["content"].startswith("Summary of earlier conversation:")
