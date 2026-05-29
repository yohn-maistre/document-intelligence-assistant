"""Personalized PageRank tiebreaker — the HippoRAG 2 idea extracted.

When hybrid retrieval (vector + BM25 + RRF) returns ties or near-ties, we
re-rank using entity centrality from klerk's own NetworkX KG. The query gets
seeded with the entities it mentions; PageRank propagates that personalization
through the graph; chunks containing high-centrality entities float up.

This is intentionally NOT HippoRAG 2 — no NV-Embed-v2 lock-in, no fork
maintenance. ~50 LOC, plain NetworkX, demonstrates the conceptual move.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import networkx as nx

from klerk.agent.kg_extract import load_graph

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class TiebreakResult:
    chunk_id: str
    original_score: float
    boosted_score: float
    matched_entities: list[str]


def _seed_entities(query: str, g: nx.MultiDiGraph) -> dict[str, float]:
    """Map query → personalization vector over graph nodes.

    Cheap matcher: any node whose name/aliases overlap a query token gets
    a uniform seed weight; absent that, return None to fall through to
    uniform-PPR (degrades to plain PageRank, still a useful centrality signal).
    """
    q_tokens = {t.lower() for t in _WORD_RE.findall(query)}
    seeds: dict[str, float] = {}
    for node_id, attrs in g.nodes(data=True):
        haystack = {attrs.get("name", "").lower()} | {
            a.lower() for a in attrs.get("aliases", [])
        } | {node_id.lower()}
        if any(tok in word for tok in q_tokens for word in haystack if word):
            seeds[node_id] = 1.0
    if not seeds:
        return {}
    weight = 1.0 / len(seeds)
    return {k: weight for k in seeds}


def chunk_centrality(
    query: str,
    *,
    alpha: float = 0.85,
) -> dict[str, float]:
    """Per-chunk centrality scores derived from the KG's PageRank.

    Each chunk's score is the sum of PageRank values of entities whose
    `evidence_chunks` includes that chunk_id. Empty graph → empty dict.
    """
    g = load_graph()
    if g.number_of_nodes() == 0:
        return {}

    seeds = _seed_entities(query, g)
    try:
        if seeds:
            scores = nx.pagerank(g, alpha=alpha, personalization=seeds)
        else:
            scores = nx.pagerank(g, alpha=alpha)
    except Exception:  # noqa: BLE001 - networkx can fail on degenerate graphs
        return {}

    chunk_scores: dict[str, float] = {}
    for node_id, attrs in g.nodes(data=True):
        node_score = scores.get(node_id, 0.0)
        for cid in attrs.get("evidence_chunks", []):
            chunk_scores[cid] = chunk_scores.get(cid, 0.0) + node_score
    return chunk_scores


def apply_tiebreak(
    results: list,  # list[RetrievedChunk] but avoid the circular import for typing
    query: str,
    *,
    weight: float = 0.15,
) -> list:
    """Mix the chunk centrality into the existing scores.

      boosted = (1 - weight) * original + weight * normalized_centrality

    `weight = 0` is a no-op (skips PPR entirely). Returns a fresh list re-sorted
    by boosted score; original_score and matched_entities are preserved on each
    item for the Studio Trace panel.
    """
    if not results or weight <= 0.0:
        return results
    centrality = chunk_centrality(query)
    if not centrality:
        return results
    max_c = max(centrality.values()) or 1.0
    out = list(results)
    for r in out:
        boost = centrality.get(r.chunk_id, 0.0) / max_c
        original = r.score
        r.score = (1.0 - weight) * original + weight * boost
    out.sort(key=lambda r: r.score, reverse=True)
    return out
