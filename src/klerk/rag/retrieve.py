"""Hybrid retrieval — vector + BM25 → RRF fusion → BGE-Reranker.

Single entry: `search_hybrid(query, k_initial, k_final)`. Returns a list of
ranked chunks with provenance (which retrievers ranked each chunk where).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from klerk.rag.embed import embed_query
from klerk.rag.fusion import rrf_by_key
from klerk.rag.store import search_bm25, search_vector


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    text: str
    locale: str
    source: str
    score: float                   # fused score (or rerank score if reranked)
    bm25_rank: int = 0             # 1-indexed; 0 = absent from BM25 results
    vector_rank: int = 0           # 1-indexed; 0 = absent from vector results
    reranked: bool = False
    rerank_score: float | None = None


def search_hybrid(
    query: str,
    *,
    k_initial: int = 16,
    k_final: int = 8,
    rerank: bool = True,
) -> list[RetrievedChunk]:
    """Hybrid retrieval.

    1. Vector search (BGE-M3 query embed → LanceDB cosine top-k_initial).
    2. BM25 search (LanceDB native FTS top-k_initial).
    3. RRF fusion (k=60) → take top k_initial fused.
    4. Optional BGE-Reranker-v2-m3 cross-encoder reorder → top k_final.

    Returns RetrievedChunk objects with per-retriever ranks for trace UI.
    """
    qv = embed_query(query)
    vec_hits = search_vector(qv, k=k_initial)
    bm25_hits = search_bm25(query, k=k_initial)

    # Index by chunk_id for stitching after fusion
    by_id: dict[str, dict[str, Any]] = {}
    for hit in vec_hits + bm25_hits:
        by_id.setdefault(hit["chunk_id"], hit)

    fused = rrf_by_key([vec_hits, bm25_hits], key="chunk_id", k=60)[:k_initial]

    results: list[RetrievedChunk] = []
    for chunk_id, score, ranks in fused:
        row = by_id[chunk_id]
        results.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                doc_id=row["doc_id"],
                text=row["text"],
                locale=row["locale"],
                source=row["source"],
                score=score,
                vector_rank=ranks[0],
                bm25_rank=ranks[1],
            )
        )

    if rerank and results:
        from klerk.rag.rerank import rerank as do_rerank

        passages = [{"chunk_id": r.chunk_id, "text": r.text} for r in results]
        reranked = do_rerank(query, passages, top_k=k_final)
        order = {r.chunk_id: (i, r.score) for i, r in enumerate(reranked)}
        results = [r for r in results if r.chunk_id in order]
        for r in results:
            idx, rscore = order[r.chunk_id]
            r.reranked = True
            r.rerank_score = rscore
            r.score = rscore
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:k_final]
    else:
        results = results[:k_final]

    return results
