"""BGE-M3 multi-head wrapper — dense (for retrieval) + ColBERT (for reranking).

BGE-M3 exposes three output heads from a single transformer: dense (1024-d
sentence vector), sparse (lexical weights), and ColBERT (token-level
multi-vector). klerk uses the dense head for LanceDB vector search and the
ColBERT head for late-interaction reranking — both served from one model
load via FlagEmbedding's `BGEM3FlagModel`.

Backends:
  - `bge-m3` (default, ~1.2GB HF download) — production multilingual quality
  - `mock`  (sandbox / CI) — deterministic hash-based pseudo-embeddings;
    bypasses Hugging Face entirely so the retrieval plumbing can be tested
    in environments without HF access. Set `KLERK_EMBED_BACKEND=mock`.

The mock backend is NOT semantic — it embeds by token hashing — so it won't
retrieve meaningfully. It's purely for verifying the LanceDB hybrid wiring,
RRF fusion, and reranker integration end-to-end without weights.
"""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache

import numpy as np

EMBED_DIM = 1024
MODEL_NAME = "BAAI/bge-m3"

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _backend() -> str:
    return os.environ.get("KLERK_EMBED_BACKEND", "bge-m3")


@lru_cache(maxsize=1)
def _bge_model():
    """Singleton BGEM3FlagModel — shared between embed and rerank paths."""
    from FlagEmbedding import BGEM3FlagModel

    device = os.environ.get("KLERK_EMBED_DEVICE", "cpu")
    use_fp16 = device.startswith("cuda")
    return BGEM3FlagModel(MODEL_NAME, devices=[device], use_fp16=use_fp16)


def _mock_vector(text: str) -> np.ndarray:
    """Deterministic pseudo-embedding: BM25-ish token hashing into EMBED_DIM dims."""
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    tokens = _WORD_RE.findall(text.lower())
    if not tokens:
        return vec
    for tok in tokens:
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        # Spread one token across 4 dims for variance
        for i in range(0, 8, 2):
            idx = int.from_bytes(h[i : i + 2], "big") % EMBED_DIM
            sign = 1.0 if h[i] % 2 == 0 else -1.0
            vec[idx] += sign
    # L2 normalize so cosine similarity behaves
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.astype(np.float32)


def embed_passages(texts: list[str], *, batch_size: int = 12) -> np.ndarray:
    """Dense embeddings for indexing. Returns (N, 1024) float32, L2-normalized."""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    if _backend() == "mock":
        return np.stack([_mock_vector(t) for t in texts]).astype(np.float32)
    out = _bge_model().encode(
        texts,
        batch_size=batch_size,
        max_length=8192,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    return np.asarray(out["dense_vecs"], dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    """Dense embedding for a single query. Returns (1024,) float32, L2-normalized."""
    if _backend() == "mock":
        return _mock_vector(text)
    out = _bge_model().encode(
        [text],
        max_length=8192,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    return np.asarray(out["dense_vecs"][0], dtype=np.float32)


def embed_with_colbert(texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
    """Token-level ColBERT vectors for late-interaction reranking.

    Returns a list of length N; each element is a (n_tokens, 1024) float32
    ndarray, L2-normalized along the last axis. Token count varies by input.

    Mock backend returns single-row matrices derived from the mock dense
    vector so the MaxSim path stays exercisable in CI without weights.
    """
    if not texts:
        return []
    if _backend() == "mock":
        return [_mock_vector(t).reshape(1, EMBED_DIM) for t in texts]
    out = _bge_model().encode(
        texts,
        batch_size=batch_size,
        max_length=8192,
        return_dense=False,
        return_sparse=False,
        return_colbert_vecs=True,
    )
    return [np.asarray(v, dtype=np.float32) for v in out["colbert_vecs"]]


def warm() -> str:
    if _backend() == "mock":
        return "mock"
    _bge_model()
    return MODEL_NAME
