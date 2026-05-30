"""Contradiction scan over the knowledge graph.

For every pair of relations sharing the same `(source, target, verb-stem)`
across different evidence chunks, we ask the LLM whether the underlying
statements are consistent. Output is a Markdown report listing each conflict
with chunk citations.

The verb-stem grouping is a cheap signal — `caps_at` vs `cap_at` vs `capped_at`
all stem to the same thing. We don't pretend to do proper morphology.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from klerk.agent.kg_extract import load_graph
from klerk.agent.pai import ask_typed
from klerk.agent.prompts.system import CONTRADICTION_PROMPT
from klerk.agent.schemas import ContradictionFinding
from klerk.rag.store import CORPUS_TABLE, open_db


@dataclass
class ConflictGroup:
    source: str
    target: str
    verb_stem: str
    evidence_chunks: list[str]


def _stem(verb: str) -> str:
    """Cheap verb normaliser — lowercase + trim common English suffixes."""
    v = verb.lower().strip()
    for suf in ("ing", "ed", "es", "s"):
        if v.endswith(suf) and len(v) > len(suf) + 2:
            return v[: -len(suf)]
    return v


def group_relations(g: nx.MultiDiGraph) -> list[ConflictGroup]:
    """Bucket relations by (source, target, verb_stem); keep groups with >1 evidence."""
    buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for u, v, edata in g.edges(data=True):
        key = (u, v, _stem(edata.get("verb", "")))
        buckets[key].append(edata.get("evidence_chunk", ""))

    out: list[ConflictGroup] = []
    for (src, tgt, stem), evs in buckets.items():
        clean_evs = sorted({e for e in evs if e})
        if len(clean_evs) >= 2:
            out.append(
                ConflictGroup(source=src, target=tgt, verb_stem=stem, evidence_chunks=clean_evs)
            )
    return out


def _chunk_text_index() -> dict[str, str]:
    """Map chunk_id → text for the LLM prompt."""
    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        return {}
    table = db.open_table(CORPUS_TABLE)
    return {row["chunk_id"]: row["text"] for row in table.to_pandas().to_dict("records")}


def scan(*, locale: str = "en") -> list[tuple[ConflictGroup, ContradictionFinding]]:
    """Run the contradiction scan. Returns one verdict per group.

    Returns groups where the LLM marked `consistent=False`, AND any group
    that explicitly listed `involved_chunks` (so the operator can audit
    edge cases the LLM was unsure about).
    """
    g = load_graph()
    if g.number_of_nodes() == 0:
        raise RuntimeError("scan: no KG — run `klerk kg extract` first.")
    groups = group_relations(g)
    if not groups:
        return []

    chunk_text = _chunk_text_index()
    results: list[tuple[ConflictGroup, ContradictionFinding]] = []
    for grp in groups:
        verdict = judge_pair(grp, chunk_text, locale=locale)
        if not verdict.consistent or verdict.contradiction:
            results.append((grp, verdict))
    return results


def judge_pair(
    grp: ConflictGroup,
    chunk_text: dict[str, str],
    *,
    locale: str = "en",
) -> ContradictionFinding:
    """Ask the LLM whether one group's cross-chunk statements contradict.

    Migrated to a PydanticAI `Agent(output_type=ContradictionFinding)`.
    Survivable: a judge error becomes a flagged (consistent=True + error note)
    finding rather than killing the scan. Always stamps `entity_or_relation`.
    """
    label = f"{grp.source} →[{grp.verb_stem}]→ {grp.target}"
    statements = "\n".join(
        f"- [{cid}] {chunk_text.get(cid, '(missing)')[:400]}"
        for cid in grp.evidence_chunks
    )
    user = (
        f"ENTITY OR RELATION: {grp.source} —[{grp.verb_stem}]→ {grp.target}\n"
        f"STATEMENTS FROM DIFFERENT CHUNKS:\n{statements}\n"
    )
    try:
        verdict = ask_typed(
            ContradictionFinding,
            system=CONTRADICTION_PROMPT,
            user=user,
            locale=locale,
            max_tokens=400,
        )
    except Exception as e:  # noqa: BLE001
        verdict = ContradictionFinding(
            consistent=True,
            contradiction=f"(scan error: {type(e).__name__}: {e})",
            involved_chunks=grp.evidence_chunks,
            entity_or_relation=label,
        )
    # Always tag the entity / relation for the report
    verdict.entity_or_relation = label
    return verdict


def render_report(findings: list[tuple[ConflictGroup, ContradictionFinding]]) -> str:
    if not findings:
        return "# Contradiction report\n\nNo contradictions detected.\n"
    lines = ["# Contradiction report", ""]
    lines.append(f"Found {len(findings)} potential contradiction(s).")
    lines.append("")
    for grp, verdict in findings:
        lines.append(f"## {verdict.entity_or_relation}")
        lines.append("")
        lines.append(f"- **status**: {'INCONSISTENT' if not verdict.consistent else 'flagged'}")
        if verdict.contradiction:
            lines.append(f"- **details**: {verdict.contradiction}")
        lines.append(f"- **chunks**: {', '.join(grp.evidence_chunks)}")
        lines.append("")
    return "\n".join(lines)


def save_report(findings: list[tuple[ConflictGroup, ContradictionFinding]]) -> Path:
    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "contradictions.md"
    path.write_text(render_report(findings), encoding="utf-8")
    return path


def _re() -> re.Pattern:  # pragma: no cover - reserved for future glob filtering
    return re.compile(".*")
