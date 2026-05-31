"""Multi-turn chat orchestrator — LangGraph `create_react_agent` over Nemotron.

Promotes /chat from a single-shot RAG handler to a tool-routing ReAct agent.
The LLM (Nemotron via an OpenAI-compatible ChatOpenAI binding) chooses among
the six klerk tools (klerk.agent.tools) each turn, with a MAX_TOOL_HOPS safety
cap. Every turn is pre-seeded with `search_hybrid` results so even a no-tool
answer is grounded.

`astream_events` yields klerk's SSE event dicts (downward-compatible with the
v5 stream; new types: session, tool_call, tool_result):

    {"event": "session",     "data": {"session_id": ...}}     # first frame
    {"event": "tool_call",   "data": {"name": ..., "args": ...}}
    {"event": "tool_result", "data": {"name": ..., "summary": ...}}
    {"event": "token",       "data": {"text": ...}}
    {"event": "citations",   "data": {"citations": [...], "confidence": ...}}
    {"event": "done",        "data": {"ttft_ms": ..., "total_ms": ..., ...}}

The agent graph + model are built lazily and cached. When Nemotron creds are
absent the caller (server.py) short-circuits before reaching here.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from functools import lru_cache

from klerk.agent.prompts.system import ORCHESTRATOR_SYSTEM
from klerk.agent.tools import ALL_TOOLS, DISPLAY_NAMES, set_session
from klerk.llm.nemotron import NemotronConfig
from klerk.llm.router import _select_model

MAX_TOOL_HOPS = 4
_CITATION_RE = re.compile(r"\[([a-zA-Z0-9_\-]+):(\d+)\]")


@lru_cache(maxsize=4)
def _chat_model(locale: str):
    """Build a ChatOpenAI bound to the Nemotron proxy (cached per locale)."""
    from langchain_openai import ChatOpenAI

    cfg = NemotronConfig.from_env()
    litellm_model, base_url = _select_model(locale)
    model_name = litellm_model.split("/", 1)[-1]
    return ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=cfg.api_key or "api-key-not-set",
        default_headers=cfg.cf_headers or None,
        temperature=0.0,
    )


@lru_cache(maxsize=4)
def _agent(locale: str):
    """Compile a create_react_agent graph over the six klerk tools."""
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(_chat_model(locale), ALL_TOOLS)


def _memory_prefix(query: str) -> str:
    """SOUL.md + recalled facts, to PREFIX the system prompt each turn.

    Guarded end-to-end: if the memory dir is missing, empty, or anything
    raises, returns "" so a chat turn never crashes on memory.
    """
    try:
        from klerk.memory import MemoryStore

        store = MemoryStore()
        soul = store.read_soul().strip()
        facts = store.recall(query, k=4)
    except Exception:  # noqa: BLE001 - memory is best-effort, never fatal
        return ""

    blocks: list[str] = []
    if soul:
        blocks.append(f"# IDENTITY (SOUL)\n{soul}")
    if facts:
        lines = "\n".join(f"- {f.fact}" for f in facts)
        blocks.append(f"# RECALLED MEMORY (durable facts; verify against sources)\n{lines}")
    return "\n\n".join(blocks)


def _confidence(answer: str, n_grounding: int) -> tuple[list[str], float]:
    """Citation extraction + a coarse confidence signal mirroring the v5 rule."""
    citations = sorted({f"{m.group(1)}:{m.group(2)}" for m in _CITATION_RE.finditer(answer)})
    if n_grounding == 0:
        return citations, 0.0
    if not citations:
        return citations, 0.0
    # Some grounded citations present → scaled confidence (cap 0.9 like v5).
    return citations, min(0.9, 0.3 + 0.1 * len(citations))


async def arun(
    query: str,
    *,
    session_id: str,
    locale: str = "en",
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict]:
    """Drive one chat turn through the orchestrator, yielding SSE event dicts."""
    import json

    start = time.perf_counter()
    set_session(session_id)
    yield {"event": "session", "data": json.dumps({"session_id": session_id})}

    # Pre-seed grounding so even a no-tool answer is corpus-backed.
    from klerk.rag.retrieve import search_hybrid

    try:
        seed_hits = search_hybrid(query, k_initial=16, k_final=8, rerank=True)
    except Exception:  # noqa: BLE001 - retrieval failure shouldn't kill the turn
        seed_hits = []
    n_grounding = len(seed_hits)
    seed_context = "\n\n".join(f"[{h.chunk_id}] {h.text}" for h in seed_hits)

    # Prefix the system prompt with klerk's SOUL + recalled memory (best-effort).
    mem_prefix = _memory_prefix(query)
    system_content = f"{mem_prefix}\n\n{ORCHESTRATOR_SYSTEM}" if mem_prefix else ORCHESTRATOR_SYSTEM

    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    if history:
        messages.extend(history)
    user_block = query
    if seed_context:
        user_block = f"{query}\n\nPRE-FETCHED EVIDENCE:\n{seed_context}"
    messages.append({"role": "user", "content": user_block})

    agent = _agent(locale)
    config = {"recursion_limit": MAX_TOOL_HOPS * 2 + 2}

    ttft_ms: float | None = None
    final_answer = ""
    hops = 0
    truncated = False

    try:
        async for event in agent.astream_events(
            {"messages": messages}, config=config, version="v2"
        ):
            kind = event.get("event")
            if kind == "on_tool_start":
                hops += 1
                if hops > MAX_TOOL_HOPS:
                    truncated = True
                    break
                name = event.get("name", "")
                yield {
                    "event": "tool_call",
                    "data": json.dumps({
                        "name": name,
                        "display_name": DISPLAY_NAMES.get(name, name),
                        "args": event.get("data", {}).get("input", {}),
                    }),
                }
            elif kind == "on_tool_end":
                name = event.get("name", "")
                out = event.get("data", {}).get("output", "")
                summary = _summarise_tool_output(out)
                yield {
                    "event": "tool_result",
                    "data": json.dumps({"name": name, "summary": summary}),
                }
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                text = getattr(chunk, "content", "") if chunk is not None else ""
                if text:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - start) * 1000
                    final_answer += text
                    yield {"event": "token", "data": json.dumps({"text": text})}
    except Exception as e:  # noqa: BLE001 - surface failures in-stream
        yield {"event": "error", "data": json.dumps({"detail": f"{type(e).__name__}: {e}"})}
        return

    citations, confidence = _confidence(final_answer, n_grounding)
    yield {
        "event": "citations",
        "data": json.dumps({"citations": citations, "confidence": confidence}),
    }

    total_ms = (time.perf_counter() - start) * 1000
    yield {
        "event": "done",
        "data": json.dumps({
            "ttft_ms": ttft_ms or total_ms,
            "total_ms": total_ms,
            "n_chunks": n_grounding,
            "tool_hops": hops,
            "truncated": truncated,
        }),
    }


def _summarise_tool_output(out) -> str:
    text = out if isinstance(out, str) else str(out)
    text = text.strip().replace("\n", " ")
    return text[:120] + ("…" if len(text) > 120 else "")
