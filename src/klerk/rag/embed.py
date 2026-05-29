"""BGE-M3 embedding wrapper — multilingual, Bahasa-strong, self-hosted.

Lazy-loads the model on first use; subsequent calls reuse the cached instance.

Backends:
  - `bge-m3` (default, ~2GB HF download) — production multilingual quality
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
    from sentence_transformers import SentenceTransformer

    device = os.environ.get("KLERK_EMBED_DEVICE", "cpu")
    return SentenceTransformer(MODEL_NAME, device=device)


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


def embed_passages(texts: list[str], *, batch_size: int = 32) -> np.ndarray:
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    if _backend() == "mock":
        return np.stack([_mock_vector(t) for t in texts]).astype(np.float32)
    vectors = _bge_model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    if _backend() == "mock":
        return _mock_vector(text)
    vec = _bge_model().encode(
        text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vec.astype(np.float32)


def warm() -> str:
    if _backend() == "mock":
        return "mock"
    _bge_model()
    return MODEL_NAME
