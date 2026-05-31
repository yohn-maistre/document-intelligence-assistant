"""Chat orchestrator (cluster 4.2).

The compiled LangGraph agent is replaced with a fake whose `astream_events`
replays canned LangChain events, so we test the SSE translation, pre-seed
grounding, citation/confidence derivation, MAX_TOOL_HOPS cap, and the tool
wrappers' activity logging — all offline.
"""

from __future__ import annotations

import json

import pytest

from klerk.agent import orchestrator, tools
from klerk.rag.retrieve import RetrievedChunk


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path / ".klerk"))
    orchestrator._chat_model.cache_clear()
    orchestrator._agent.cache_clear()
    yield


def _hit(chunk_id, text):
    return RetrievedChunk(
        chunk_id=chunk_id, doc_id=chunk_id.split(":")[0], text=text,
        locale="en", source="test", score=1.0,
    )


class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeAgent:
    """Replays a scripted list of LangChain astream_events dicts."""

    def __init__(self, events):
        self._events = events

    async def astream_events(self, _inputs, *, config=None, version=None):
        for ev in self._events:
            yield ev


def _drain(gen):
    """Collect an async generator into (event_name -> list[data]) + order."""
    import asyncio

    async def go():
        out = []
        async for e in gen:
            out.append((e["event"], json.loads(e["data"])))
        return out

    return asyncio.run(go())


def _patch_seed(monkeypatch, hits):
    monkeypatch.setattr(
        "klerk.rag.retrieve.search_hybrid",
        lambda *a, **k: hits,
    )


def test_emits_session_first_and_done_last(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "grounding text")])
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("Answer ")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("[d:0]")}},
    ]
    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _FakeAgent(events))

    out = _drain(orchestrator.arun("q", session_id="s1", locale="en"))
    names = [n for n, _ in out]
    assert names[0] == "session"
    assert out[0][1]["session_id"] == "s1"
    assert names[-1] == "done"
    assert "citations" in names
    # tokens streamed through
    tokens = [d["text"] for n, d in out if n == "token"]
    assert "".join(tokens) == "Answer [d:0]"


def test_citations_and_confidence_from_answer(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "x"), _hit("d:1", "y")])
    events = [{"event": "on_chat_model_stream", "data": {"chunk": _Chunk("see [d:0] and [d:1]")}}]
    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _FakeAgent(events))

    out = _drain(orchestrator.arun("q", session_id="s", locale="en"))
    cite = next(d for n, d in out if n == "citations")
    assert cite["citations"] == ["d:0", "d:1"]
    assert cite["confidence"] > 0.0


def test_no_citations_means_zero_confidence(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "x")])
    events = [{"event": "on_chat_model_stream", "data": {"chunk": _Chunk("ungrounded answer")}}]
    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _FakeAgent(events))

    out = _drain(orchestrator.arun("q", session_id="s"))
    cite = next(d for n, d in out if n == "citations")
    assert cite["confidence"] == 0.0


def test_tool_call_and_result_events(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "x")])
    events = [
        {"event": "on_tool_start", "name": "search_hybrid",
         "data": {"input": {"query": "exit criteria"}}},
        {"event": "on_tool_end", "name": "search_hybrid",
         "data": {"output": "[d:0] some chunk text here"}},
        {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("done [d:0]")}},
    ]
    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _FakeAgent(events))

    out = _drain(orchestrator.arun("q", session_id="s"))
    tc = next(d for n, d in out if n == "tool_call")
    assert tc["name"] == "search_hybrid"
    assert tc["display_name"] == "klerk search hybrid"
    tr = next(d for n, d in out if n == "tool_result")
    assert tr["name"] == "search_hybrid"
    assert "chunk text" in tr["summary"]


def test_max_tool_hops_truncates(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "x")])
    # 5 tool starts > MAX_TOOL_HOPS (4) → truncation
    events = []
    for i in range(orchestrator.MAX_TOOL_HOPS + 1):
        events.append({"event": "on_tool_start", "name": "search_hybrid",
                       "data": {"input": {"query": f"q{i}"}}})
        events.append({"event": "on_tool_end", "name": "search_hybrid",
                       "data": {"output": "x"}})
    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _FakeAgent(events))

    out = _drain(orchestrator.arun("q", session_id="s"))
    done = next(d for n, d in out if n == "done")
    assert done["truncated"] is True


def test_history_is_included(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "x")])
    captured = {}

    class _CapturingAgent:
        async def astream_events(self, inputs, *, config=None, version=None):
            captured["messages"] = inputs["messages"]
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("ok")}}

    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _CapturingAgent())
    history = [{"role": "user", "content": "earlier q"}, {"role": "assistant", "content": "earlier a"}]
    _drain(orchestrator.arun("now", session_id="s", history=history))

    contents = [m["content"] for m in captured["messages"]]
    assert any("earlier q" in c for c in contents)
    # pre-fetched evidence appended to the live user message
    assert any("PRE-FETCHED EVIDENCE" in c for c in contents)


def test_error_in_stream_is_surfaced(monkeypatch):
    _patch_seed(monkeypatch, [_hit("d:0", "x")])

    class _BoomAgent:
        async def astream_events(self, _inputs, *, config=None, version=None):
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("partial")}}
            raise RuntimeError("model exploded")

    monkeypatch.setattr(orchestrator, "_agent", lambda locale: _BoomAgent())
    out = _drain(orchestrator.arun("q", session_id="s"))
    assert any(n == "error" for n, _ in out)


# ─── Tool wrappers + activity log ────────────────────────────────────────────
def test_search_hybrid_tool_logs_activity(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "klerk.rag.retrieve.search_hybrid",
        lambda *a, **k: [_hit("d:0", "alpha"), _hit("d:1", "beta")],
    )
    tools.set_session("sess-9")
    result = tools.search_hybrid.invoke({"query": "anything"})
    assert "[d:0]" in result and "[d:1]" in result

    log = (tmp_path / ".klerk" / "activity-log.jsonl").read_text().splitlines()
    rec = json.loads(log[-1])
    assert rec["tool"] == "search_hybrid"
    assert rec["display_name"] == "klerk search hybrid"
    assert rec["status"] == "ok"
    assert rec["summary"] == "2 chunks"
    assert rec["session_id"] == "sess-9"


def test_tool_error_is_returned_as_text_and_logged(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("retrieval down")

    monkeypatch.setattr("klerk.rag.retrieve.search_hybrid", boom)
    tools.set_session(None)
    result = tools.search_hybrid.invoke({"query": "x"})
    assert "TOOL ERROR" in result and "retrieval down" in result

    rec = json.loads((tmp_path / ".klerk" / "activity-log.jsonl").read_text().splitlines()[-1])
    assert rec["status"] == "error"
