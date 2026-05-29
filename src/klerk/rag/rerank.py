"""BGE-Reranker-v2-m3 — multilingual cross-encoder for top-k reordering.

Cross-encoder = (query, passage) → score in one forward pass. Slower per pair
than bi-encoder retrieval but dramatically higher precision for the small
top-k window that survives initial retrieval.

Backends:
  - `bge-reranker-v2-m3` (default, ~600MB HF download) — production quality
  - `mock` — Jaccard token overlap; bypasses HF for sandbox/CI use.
    Activated by KLERK_RERANK_BACKEND=mock OR by KLERK_EMBED_BACKEND=mock
    (so a single env-var flips the full pipeline into offline mode).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache

MODEL_NAME = "BAAI/bge-reranker-v2-m3"
_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class RerankResult:
    """One passage with its cross-encoder relevance score."""

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
    return "bge-reranker-v2-m3"


@lru_cache(maxsize=1)
def _bge_model():
    from sentence_transformers import CrossEncoder

    device = os.environ.get("KLERK_RERANK_DEVICE", "cpu")
    return CrossEncoder(MODEL_NAME, device=device)


def _mock_score(query: str, passage: str) -> float:
    """Jaccard token overlap — cheap, deterministic, ordering-meaningful."""
    q = set(_WORD_RE.findall(query.lower()))
    p = set(_WORD_RE.findall(passage.lower()))
    if not q or not p:
        return 0.0
    return len(q & p) / len(q | p)


def rerank(
    query: str,
    passages: list[dict],
    *,
    text_key: str = "text",
    id_key: str = "chunk_id",
    top_k: int | None = None,
) -> list[RerankResult]:
    if not passages:
        return []

    if _backend() == "mock":
        scores = [_mock_score(query, p[text_key]) for p in passages]
    else:
        pairs = [(query, p[text_key]) for p in passages]
        scores = _bge_model().predict(pairs, show_progress_bar=False)

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
    _bge_model()
    return MODEL_NAME
