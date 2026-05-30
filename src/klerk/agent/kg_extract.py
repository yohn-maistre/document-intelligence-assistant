"""Knowledge graph extraction — Pydantic AI structured output → NetworkX.

For each chunk, we ask the LLM to emit entities + relations as JSON conforming
to `ExtractedGraph`. The aggregator merges per-chunk extractions into a single
NetworkX DiGraph and persists to JSON. Entities are deduplicated by canonical
id; relations carry their `evidence_chunk` for citation traceback during
contradiction scans.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from klerk.agent.pai import ask_typed
from klerk.agent.prompts.system import KG_EXTRACT_PROMPT
from klerk.agent.schemas import ExtractedGraph


def _kg_dir() -> Path:
    p = Path(os.environ.get("KLERK_KG_DIR", "data/kg"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _kg_path() -> Path:
    return _kg_dir() / "graph.json"


@dataclass
class KgStats:
    n_entities: int
    n_relations: int
    n_chunks_seen: int


# ─── Per-chunk extraction ────────────────────────────────────────────────────
def extract_chunk(chunk_id: str, text: str, *, locale: str = "en") -> ExtractedGraph:
    """One LLM call → entities + relations for one chunk."""
    user = (
        f"CHUNK_ID: {chunk_id}\n"
        f"LOCALE: {locale}\n"
        f"PASSAGE:\n{text}\n\n"
        "Set every relation's `evidence_chunk` to the CHUNK_ID above."
    )
    return ask_typed(
        ExtractedGraph,
        system=KG_EXTRACT_PROMPT,
        user=user,
        locale=locale,
        max_tokens=1500,
    )


# ─── Build / persist ─────────────────────────────────────────────────────────
def build_graph(
    chunks: Iterable[tuple[str, str, str]],
) -> nx.MultiDiGraph:
    """Build a fresh KG from `(chunk_id, text, locale)` triples.

    Uses MultiDiGraph so different relations between the same pair of entities
    coexist (e.g. `signed_with` and `references`).
    """
    g = nx.MultiDiGraph()
    seen_chunks = 0
    for chunk_id, text, locale in chunks:
        try:
            extracted = extract_chunk(chunk_id, text, locale=locale)
        except Exception as e:  # noqa: BLE001
            g.graph.setdefault("extraction_errors", []).append(
                {"chunk_id": chunk_id, "error": f"{type(e).__name__}: {e}"}
            )
            continue
        seen_chunks += 1
        _merge_into(g, extracted, chunk_id=chunk_id)
    g.graph["n_chunks_seen"] = seen_chunks
    return g


def _merge_into(g: nx.MultiDiGraph, extracted: ExtractedGraph, *, chunk_id: str) -> None:
    for ent in extracted.entities:
        if g.has_node(ent.id):
            existing = g.nodes[ent.id]
            existing.setdefault("aliases", set()).update(ent.aliases)
            existing.setdefault("evidence_chunks", set()).add(chunk_id)
            # First-write-wins on type/name to avoid LLM volatility
        else:
            g.add_node(
                ent.id,
                type=ent.type,
                name=ent.name,
                aliases=set(ent.aliases),
                evidence_chunks={chunk_id},
            )
    for rel in extracted.relations:
        if not (g.has_node(rel.source) and g.has_node(rel.target)):
            # Skip relations whose endpoints we didn't see as entities — guards
            # against LLM-hallucinated dangling edges.
            continue
        g.add_edge(
            rel.source,
            rel.target,
            key=f"{rel.verb}@{rel.evidence_chunk or chunk_id}",
            verb=rel.verb,
            evidence_chunk=rel.evidence_chunk or chunk_id,
        )


def save_graph(g: nx.MultiDiGraph) -> Path:
    """Serialize to JSON (NetworkX `node_link_data` + set→list normalisation)."""
    data = nx.node_link_data(g, edges="edges")
    for node in data.get("nodes", []):
        for k, v in list(node.items()):
            if isinstance(v, set):
                node[k] = sorted(v)
    p = _kg_path()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return p


def load_graph() -> nx.MultiDiGraph:
    p = _kg_path()
    if not p.exists():
        return nx.MultiDiGraph()
    data = json.loads(p.read_text())
    g = nx.node_link_graph(data, multigraph=True, directed=True, edges="edges")
    # Re-hydrate sets we flattened on save
    for _, attrs in g.nodes(data=True):
        for k in ("aliases", "evidence_chunks"):
            if k in attrs and isinstance(attrs[k], list):
                attrs[k] = set(attrs[k])
    return g


def stats(g: nx.MultiDiGraph | None = None) -> KgStats:
    g = g if g is not None else load_graph()
    return KgStats(
        n_entities=g.number_of_nodes(),
        n_relations=g.number_of_edges(),
        n_chunks_seen=g.graph.get("n_chunks_seen", 0),
    )


# ─── Convenience: rebuild from the indexed corpus ────────────────────────────
def rebuild_from_corpus() -> KgStats:
    """Pull every chunk from LanceDB and build a fresh KG over them."""
    from klerk.rag.store import CORPUS_TABLE, open_db

    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        raise RuntimeError(
            "rebuild_from_corpus: no corpus table — run `klerk index build` first."
        )
    rows = db.open_table(CORPUS_TABLE).to_pandas()
    triples = [
        (row["chunk_id"], row["text"], row.get("locale", "und"))
        for _, row in rows.iterrows()
    ]
    g = build_graph(triples)
    save_graph(g)
    return stats(g)
