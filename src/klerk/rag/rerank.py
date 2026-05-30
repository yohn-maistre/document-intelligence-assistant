"""Late-interaction reranking via BGE-M3's ColBERT head — no separate model.

BGE-M3 is a 3-headed model (dense + sparse + ColBERT). The dense head powers
LanceDB vector retrieval; the ColBERT head powers reranking. This module
reuses the BGE-M3 instance already loaded by `klerk.rag.embed` and computes
MaxSim scores between query and passage token-level vectors:

    MaxSim(Q, D) = Σ_{q_i ∈ Q} max_{d_j ∈ D} dot(q_i, d_j)

Both Q and D come L2-normalized from BGE-M3, so dot product = cosine.
Score range: [0, |Q|]. Higher = more relevant.

Backends:
  - `bge-m3` (default) — ColBERT-head MaxSim, shares the embed-side load
  - `mock` — Jaccard token overlap; bypasses HF for sandbox/CI use.
    Activated by KLERK_RERANK_BACKEND=mock OR by KLERK_EMBED_BACKEND=mock
    (so a single env-var flips the full pipeline into offline mode).

Graceful degradation: when the embed backend has no ColBERT head (e.g.
`KLERK_EMBED_BACKEND=remote`), `embed_with_colbert` raises RuntimeError and
this module falls back to the upstream RRF fusion order instead of reranking.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import numpy as np

from klerk.rag.embed import embed_with_colbert

MODEL_NAME = "BAAI/bge-m3 (ColBERT head)"
_WORD_RE = re.compile(r"\w+", re.UNICODE)

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """One passage with its late-interaction relevance score."""

    chunk_id: str
    text: str
    score: float
    original_rank: int  # 1-indexed rank pre-rerank


def _backend() -> str:
    explicit = os.environ.get("KLERK_RERANK_BACKEND")
    if explicit:
        return explicit
    # Default: track the embed backend — `KLERK_EMBED_BACKEND=mock` implies mock rerank too
    if os.environ.get("KLERK_EMBED_BACKEND") == "mock":
        return "mock"
    return "bge-m3"


def _mock_score(query: str, passage: str) -> float:
    """Jaccard token overlap — cheap, deterministic, ordering-meaningful."""
    q = set(_WORD_RE.findall(query.lower()))
    p = set(_WORD_RE.findall(passage.lower()))
    if not q or not p:
        return 0.0
    return len(q & p) / len(q | p)


def _maxsim(q_vecs: np.ndarray, p_vecs: np.ndarray) -> float:
    """ColBERT MaxSim. Inputs are L2-normalized token-level matrices."""
    if q_vecs.size == 0 or p_vecs.size == 0:
        return 0.0
    sims = q_vecs @ p_vecs.T              # (n_q, n_p) cosine-equivalent
    return float(sims.max(axis=1).sum())  # max over passage tokens, sum over query tokens


def rerank(
    query: str,
    passages: list[dict],
    *,
    text_key: str = "text",
    id_key: str = "chunk_id",
    top_k: int | None = None,
) -> list[RerankResult]:
    """Reorder `passages` by relevance to `query`.

    Same input/output shape as the v4 cross-encoder reranker — the only
    difference is the scoring backend (BGE-M3 ColBERT MaxSim instead of a
    separate BGE-Reranker-v2-m3 model load).

    When ColBERT vectors are unavailable (remote embed backend), the upstream
    RRF fusion order is preserved instead of reranking.
    """
    if not passages:
        return []

    if _backend() == "mock":
        scores: list[float] = [_mock_score(query, p[text_key]) for p in passages]
    else:
        try:
            q_colbert = embed_with_colbert([query])[0]
            p_colberts = embed_with_colbert([p[text_key] for p in passages])
            scores = [_maxsim(q_colbert, pv) for pv in p_colberts]
        except RuntimeError as exc:
            # Remote embed backend has no ColBERT head — preserve the upstream
            # RRF fusion order instead of reranking. Synthetic descending
            # scores keep ordering stable for downstream consumers.
            logger.warning("rerank: ColBERT unavailable (%s); falling back to RRF order", exc)
            fallback = [
                RerankResult(
                    chunk_id=p[id_key],
                    text=p[text_key],
                    score=float(len(passages) - i),
                    original_rank=i + 1,
                )
                for i, p in enumerate(passages)
            ]
            return fallback[:top_k] if top_k is not None else fallback

    out = [
        RerankResult(
            chunk_id=p[id_key],
            text=p[text_key],
            score=float(s),
            original_rank=i + 1,
        )
        for i, (p, s) in enumerate(zip(passages, scores, strict=False))
    ]
    out.sort(key=lambda r: r.score, reverse=True)
    if top_k is not None:
        out = out[:top_k]
    return out


def warm() -> str:
    if _backend() == "mock":
        return "mock"
    from klerk.rag.embed import warm as embed_warm

    embed_warm()
    return MODEL_NAME
