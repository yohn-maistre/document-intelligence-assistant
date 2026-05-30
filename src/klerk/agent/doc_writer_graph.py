"""LangGraph spine for the doc-writer (capability D).

The sequential pipeline lives in `klerk.agent.doc_writer` as a set of stage
functions. This module arranges those same stages as an explicit StateGraph
so the headline 2026-paradigm extract — **parallel competing drafters** —
shows up as a graph-level fan-out rather than a buried ThreadPoolExecutor:

    scope ──┬──▶ drafter_a ──┐
            │                 ├──▶ citation_tracer ──▶ adjudicator ──▶ critic ──▶ END
            └──▶ drafter_b ──┘

`drafter_a` and `drafter_b` are siblings fanned out from `scope` and joined
at `citation_tracer`; LangGraph runs them concurrently and waits for both
before the join. Each writes a disjoint state key (`draft_a` / `draft_b`) so
the parallel updates never collide.

Checkpointing has two layers:
  - LangGraph `MemorySaver` keyed by `thread_id=run_id` — in-process
    checkpoint semantics for the compiled graph.
  - A durable pickle-backed SQLite store at `.klerk/checkpoints.db` — so a
    fresh process can `klerk write --resume <run_id>` and get the finished
    doc back. (LangGraph's SqliteSaver ships in a separate package we don't
    pull in; this keeps the dependency surface flat while still giving real
    cross-process resume of completed runs.)
"""

from __future__ import annotations

import os
import pickle
import sqlite3
import uuid
from pathlib import Path
from typing import Any, TypedDict

from klerk.agent import doc_writer as dw
from klerk.agent.schemas import RubricScores


# ─── Graph state ─────────────────────────────────────────────────────────────
class DocWriterState(TypedDict, total=False):
    """Per-run state. total=False so partially-built states stay valid."""

    topic: str
    locale: str
    n_sections: int
    k_per_section: int
    run_id: str

    # scope
    sections: list[Any]                 # list[ProposalSection]
    scope: Any                          # ProposalScope
    evidence: dict[int, list[Any]]      # section idx → list[RetrievedChunk]

    # drafters (disjoint keys → safe parallel fan-out)
    draft_a: dict[int, Any]             # idx → DraftedSection
    draft_b: dict[int, Any]

    # citation tracer
    cite_a: dict[int, dict[str, bool]]
    cite_b: dict[int, dict[str, bool]]

    # adjudicator
    adjudications: dict[int, Any]       # idx → Adjudication

    # critic
    rubrics: dict[int, Any]             # idx → RubricScores
    proposal: Any                       # assembled Proposal


# ─── Nodes ───────────────────────────────────────────────────────────────────
def _scope(state: DocWriterState) -> DocWriterState:
    scope = dw.plan_scope(
        state["topic"],
        n_sections=state.get("n_sections", 3),
        locale=state.get("locale", "en"),
    )
    evidence = {
        i: dw.gather_evidence(section, k=state.get("k_per_section", 8))
        for i, section in enumerate(scope.sections)
    }
    return {**state, "scope": scope, "sections": list(scope.sections), "evidence": evidence}


def _drafter_a(state: DocWriterState) -> DocWriterState:
    locale = state.get("locale", "en")
    evidence = state.get("evidence", {})
    drafts = {
        i: dw._draft_section(section, evidence.get(i, []), drafter_id="A", locale=locale)
        for i, section in enumerate(state.get("sections", []))
    }
    return {"draft_a": drafts}


def _drafter_b(state: DocWriterState) -> DocWriterState:
    locale = state.get("locale", "en")
    evidence = state.get("evidence", {})
    drafts = {
        i: dw._draft_section(section, evidence.get(i, []), drafter_id="B", locale=locale)
        for i, section in enumerate(state.get("sections", []))
    }
    return {"draft_b": drafts}


def _citation_tracer(state: DocWriterState) -> DocWriterState:
    evidence = state.get("evidence", {})
    draft_a = state.get("draft_a", {})
    draft_b = state.get("draft_b", {})
    cite_a = {i: dw.trace_citations(draft_a[i], evidence.get(i, [])) for i in draft_a}
    cite_b = {i: dw.trace_citations(draft_b[i], evidence.get(i, [])) for i in draft_b}
    return {**state, "cite_a": cite_a, "cite_b": cite_b}


def _adjudicator(state: DocWriterState) -> DocWriterState:
    locale = state.get("locale", "en")
    draft_a = state.get("draft_a", {})
    draft_b = state.get("draft_b", {})
    adjudications = {
        i: dw.adjudicate(section, draft_a[i], draft_b[i], locale=locale)
        for i, section in enumerate(state.get("sections", []))
    }
    return {**state, "adjudications": adjudications}


def _critic(state: DocWriterState) -> DocWriterState:
    locale = state.get("locale", "en")
    sections = state.get("sections", [])
    evidence = state.get("evidence", {})
    draft_a = state.get("draft_a", {})
    draft_b = state.get("draft_b", {})
    cite_a = state.get("cite_a", {})
    cite_b = state.get("cite_b", {})
    adjudications = state.get("adjudications", {})

    rounds: list[dw.SectionRound] = []
    rubrics: dict[int, RubricScores] = {}
    for i, section in enumerate(sections):
        adj = adjudications[i]
        winning = draft_a[i] if adj.winner == "A" else draft_b[i]
        cite_check = cite_a[i] if adj.winner == "A" else cite_b[i]
        rubric = dw.score_rubric(section, winning, evidence.get(i, []), cite_check, locale=locale)
        rubrics[i] = rubric
        rounds.append(
            dw.SectionRound(
                section=section,
                retrieved=evidence.get(i, []),
                draft_a=draft_a[i],
                draft_b=draft_b[i],
                adjudication=adj,
                rubric=rubric,
                cite_check_a=cite_a.get(i, {}),
                cite_check_b=cite_b.get(i, {}),
            )
        )

    proposal = dw.assemble_proposal(
        topic=state["topic"],
        locale=locale,
        scope=state["scope"],
        rounds=rounds,
    )
    return {**state, "rubrics": rubrics, "proposal": proposal}


# ─── Durable checkpoint store (cross-process resume) ─────────────────────────
def _checkpoint_db() -> Path:
    p = Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "checkpoints.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_checkpoint_db())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS doc_writer "
        "(run_id TEXT PRIMARY KEY, payload BLOB NOT NULL, created_at TEXT NOT NULL)"
    )
    return conn


def save_checkpoint(run_id: str, proposal: Any) -> None:
    from datetime import datetime, timezone

    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO doc_writer (run_id, payload, created_at) VALUES (?, ?, ?)",
            (run_id, pickle.dumps(proposal), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def load_checkpoint(run_id: str) -> Any | None:
    db = _checkpoint_db()
    if not db.exists():
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload FROM doc_writer WHERE run_id = ?", (run_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        return pickle.loads(row[0])
    except Exception:  # noqa: BLE001 - corrupt checkpoint → treat as absent
        return None


# ─── Graph build + cached compile ────────────────────────────────────────────
_compiled_graph = None


def _build_graph():
    """Build + compile the StateGraph with a MemorySaver checkpointer. Cached."""
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    graph = StateGraph(DocWriterState)
    graph.add_node("scope", _scope)
    graph.add_node("drafter_a", _drafter_a)
    graph.add_node("drafter_b", _drafter_b)
    graph.add_node("citation_tracer", _citation_tracer)
    graph.add_node("adjudicator", _adjudicator)
    graph.add_node("critic", _critic)

    graph.set_entry_point("scope")
    # Fan-out: scope → {drafter_a, drafter_b} run in parallel …
    graph.add_edge("scope", "drafter_a")
    graph.add_edge("scope", "drafter_b")
    # … fan-in: citation_tracer waits for both drafters.
    graph.add_edge("drafter_a", "citation_tracer")
    graph.add_edge("drafter_b", "citation_tracer")
    graph.add_edge("citation_tracer", "adjudicator")
    graph.add_edge("adjudicator", "critic")
    graph.add_edge("critic", END)

    _compiled_graph = graph.compile(checkpointer=MemorySaver())
    return _compiled_graph


# ─── Public entrypoint ───────────────────────────────────────────────────────
def run(
    topic: str,
    *,
    n_sections: int = 3,
    k_per_section: int = 8,
    locale: str = "en",
    run_id: str | None = None,
    resume: bool = False,
) -> Any:
    """Run the doc-writer graph. Returns the assembled `Proposal`.

    With `resume=True` and a known `run_id`, returns the durably-checkpointed
    completed proposal instead of re-running. A resume against an unknown
    run_id falls through to a fresh run under that id.
    """
    run_id = run_id or uuid.uuid4().hex
    if resume:
        cached = load_checkpoint(run_id)
        if cached is not None:
            return cached

    graph = _build_graph()
    initial: DocWriterState = {
        "topic": topic,
        "locale": locale,
        "n_sections": n_sections,
        "k_per_section": k_per_section,
        "run_id": run_id,
    }
    final = graph.invoke(initial, config={"configurable": {"thread_id": run_id}})
    proposal = final["proposal"]
    save_checkpoint(run_id, proposal)
    return proposal


def export_diagram(path: Path | None = None) -> Path:
    """Write the Mermaid diagram of the compiled graph (README keeps it synced)."""
    path = path or Path("docs/doc-writer-graph.mmd")
    path.parent.mkdir(parents=True, exist_ok=True)
    graph = _build_graph()
    try:
        mermaid = graph.get_graph().draw_mermaid()
    except Exception:  # pragma: no cover - older langgraph versions
        mermaid = (
            "graph TD\n"
            "  scope --> drafter_a\n"
            "  scope --> drafter_b\n"
            "  drafter_a --> citation_tracer\n"
            "  drafter_b --> citation_tracer\n"
            "  citation_tracer --> adjudicator\n"
            "  adjudicator --> critic\n"
            "  critic --> __end__\n"
        )
    path.write_text(mermaid)
    return path
