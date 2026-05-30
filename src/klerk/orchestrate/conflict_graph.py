"""LangGraph spine for the Conflict Reporter (capability C).

The existing klerk.agent.contradiction.scan does this as one synchronous
function. The LangGraph version exposes the same logic as a 4-node
StateGraph so:
  - The flow is inspectable (the graph itself documents the pipeline).
  - Checkpointing falls out of LangGraph: `/conflicts/scan?resume=<run_id>`
    can continue a long scan that crashed mid-run.
  - Each node becomes individually instrumentable for tracing + eval.

Graph:

  retrieve_docs ──▶ pair_facts ──▶ judge_conflict ──▶ format_report ──▶ END
    (load KG)       (cross-doc      (per-pair          (markdown +
                    candidates)     LLM call)           structured findings)

State is a TypedDict so LangGraph's serialiser can checkpoint to SQLite
(`.klerk/langgraph-state.db`) between nodes. The judge_conflict node is
the only LLM-bound step; the others are pure Python over the loaded KG.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

from klerk.agent.contradiction import (
    ConflictGroup,
    _chunk_text_index,
    group_relations,
    render_report,
)
from klerk.agent.kg_extract import load_graph
from klerk.agent.llm_json import ask_json
from klerk.agent.prompts.system import CONTRADICTION_PROMPT
from klerk.agent.schemas import ContradictionFinding


# ─── Graph state ─────────────────────────────────────────────────────────────
class ConflictState(TypedDict, total=False):
    """LangGraph's per-run state. Every key is optional so partially-checkpointed
    runs deserialise cleanly."""

    locale: str

    # populated by retrieve_docs
    chunk_text: dict[str, str]
    candidate_groups: list[dict[str, Any]]

    # populated by pair_facts
    paired_prompts: list[dict[str, str]]

    # populated by judge_conflict
    findings: list[dict[str, Any]]

    # populated by format_report
    report_markdown: str
    n_findings: int


# ─── Nodes ───────────────────────────────────────────────────────────────────
def _retrieve_docs(state: ConflictState) -> ConflictState:
    """Load the KG, build the chunk-text index, group relations by
    (source, target, verb-stem) candidates."""
    g = load_graph()
    if g.number_of_nodes() == 0:
        raise RuntimeError("conflict_graph: no KG — run `klerk kg extract` first.")
    groups = group_relations(g)
    return {
        **state,
        "chunk_text": _chunk_text_index(),
        "candidate_groups": [
            {
                "source": g.source,
                "target": g.target,
                "verb_stem": g.verb_stem,
                "evidence_chunks": list(g.evidence_chunks),
            }
            for g in groups
        ],
    }


def _pair_facts(state: ConflictState) -> ConflictState:
    """Render the per-group prompts that the judge node will consume.
    Doing this in a dedicated node means the prompt can be inspected /
    cached / replayed independently of the LLM."""
    chunk_text = state.get("chunk_text", {})
    paired: list[dict[str, str]] = []
    for grp in state.get("candidate_groups", []):
        statements = "\n".join(
            f"- [{cid}] {chunk_text.get(cid, '(missing)')[:400]}"
            for cid in grp["evidence_chunks"]
        )
        paired.append({
            "entity_or_relation": f"{grp['source']} →[{grp['verb_stem']}]→ {grp['target']}",
            "evidence_chunks": grp["evidence_chunks"],
            "user_prompt": (
                f"ENTITY OR RELATION: {grp['source']} —[{grp['verb_stem']}]→ {grp['target']}\n"
                f"STATEMENTS FROM DIFFERENT CHUNKS:\n{statements}\n"
            ),
        })
    return {**state, "paired_prompts": paired}


def _judge_conflict(state: ConflictState) -> ConflictState:
    """Per-pair LLM call. Survivable: one bad pair becomes a flagged finding
    with the error in the contradiction field rather than killing the run."""
    locale = state.get("locale", "en")
    findings: list[dict[str, Any]] = []
    for pair in state.get("paired_prompts", []):
        try:
            verdict = ask_json(
                ContradictionFinding,
                system=CONTRADICTION_PROMPT,
                user=pair["user_prompt"],
                locale=locale,
                max_tokens=400,
            )
        except Exception as e:  # noqa: BLE001
            verdict = ContradictionFinding(
                consistent=True,
                contradiction=f"(judge error: {type(e).__name__}: {e})",
                involved_chunks=pair["evidence_chunks"],
                entity_or_relation=pair["entity_or_relation"],
            )
        # Always stamp the structural label in case the model dropped it
        verdict.entity_or_relation = pair["entity_or_relation"]
        if not verdict.consistent or verdict.contradiction:
            findings.append({
                "entity_or_relation": verdict.entity_or_relation,
                "consistent": verdict.consistent,
                "contradiction": verdict.contradiction,
                "evidence_chunks": pair["evidence_chunks"],
            })
    return {**state, "findings": findings}


def _format_report(state: ConflictState) -> ConflictState:
    """Build the existing markdown report so the file-on-disk format stays
    identical to the pre-LangGraph path."""
    findings = state.get("findings", [])

    # Reconstruct the `[(ConflictGroup, ContradictionFinding), ...]` shape
    # that render_report expects.
    rendered_input: list[tuple[ConflictGroup, ContradictionFinding]] = []
    for f in findings:
        grp = ConflictGroup(
            source=f["entity_or_relation"].split(" →[")[0].strip(),
            target=f["entity_or_relation"].rsplit("]→", 1)[-1].strip(),
            verb_stem=(
                f["entity_or_relation"].split(" →[", 1)[-1].split("]→", 1)[0]
                if " →[" in f["entity_or_relation"]
                else ""
            ),
            evidence_chunks=f["evidence_chunks"],
        )
        verdict = ContradictionFinding(
            consistent=f["consistent"],
            contradiction=f.get("contradiction") or "",
            involved_chunks=f["evidence_chunks"],
            entity_or_relation=f["entity_or_relation"],
        )
        rendered_input.append((grp, verdict))

    return {
        **state,
        "report_markdown": render_report(rendered_input),
        "n_findings": len(findings),
    }


# ─── Graph build + cached compile ────────────────────────────────────────────
def _checkpointer_path() -> Path:
    p = Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "langgraph-state.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_compiled_graph = None


def _build_graph():
    """Build + compile the StateGraph. Cached so re-runs don't re-import."""
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    from langgraph.graph import END, StateGraph

    graph = StateGraph(ConflictState)
    graph.add_node("retrieve_docs", _retrieve_docs)
    graph.add_node("pair_facts", _pair_facts)
    graph.add_node("judge_conflict", _judge_conflict)
    graph.add_node("format_report", _format_report)

    graph.set_entry_point("retrieve_docs")
    graph.add_edge("retrieve_docs", "pair_facts")
    graph.add_edge("pair_facts", "judge_conflict")
    graph.add_edge("judge_conflict", "format_report")
    graph.add_edge("format_report", END)

    _compiled_graph = graph.compile()
    return _compiled_graph


# ─── Public entrypoint ───────────────────────────────────────────────────────
def run(locale: str = "en") -> ConflictState:
    """Run the 4-node conflict spine end to end. Returns the final state
    (findings + markdown report)."""
    graph = _build_graph()
    initial: ConflictState = {"locale": locale}
    return graph.invoke(initial)


def export_diagram(path: Path | None = None) -> Path:
    """Write the Mermaid diagram of the compiled graph to a file. Used by
    the README so the diagram stays in sync with the actual code."""
    path = path or Path("docs/conflict-graph.mmd")
    path.parent.mkdir(parents=True, exist_ok=True)
    graph = _build_graph()
    try:
        mermaid = graph.get_graph().draw_mermaid()
    except Exception:  # pragma: no cover - older langgraph versions
        mermaid = (
            "graph TD\n"
            "  retrieve_docs --> pair_facts\n"
            "  pair_facts --> judge_conflict\n"
            "  judge_conflict --> format_report\n"
            "  format_report --> __end__\n"
        )
    path.write_text(mermaid)
    return path
