"""BGE-M3 multi-head wrapper — dense (for retrieval) + ColBERT (for reranking).

BGE-M3 exposes three output heads from a single transformer: dense (1024-d
sentence vector), sparse (lexical weights), and ColBERT (token-level
multi-vector). klerk uses the dense head for LanceDB vector search and the
ColBERT head for late-interaction reranking — both served from one model
load via FlagEmbedding's `BGEM3FlagModel`.

Backends (selected via `KLERK_EMBED_BACKEND`):
  - `local` (a.k.a. `bge-m3`, the default; ~1.2GB HF download) — production
    multilingual quality. Implemented by `LocalBGE`. Requires the `local`
    extra (`FlagEmbedding` / `torch` / `transformers`); a missing dependency
    raises an actionable install hint rather than a bare ImportError.
  - `remote` — provider-neutral OpenAI-compatible `/embeddings` endpoint
    (DeepInfra / Jina / OpenRouter / …). For constrained-env demos where
    pulling 1.2GB of weights is impractical. Dense-only: the ColBERT head
    has no remote equivalent, so `embed_with_colbert` raises and the
    reranker falls back to RRF order. Configured via `KLERK_EMBED_REMOTE_URL`,
    `KLERK_EMBED_REMOTE_KEY`, `KLERK_EMBED_REMOTE_MODEL`. The remote model
    MUST emit 1024-d vectors to match the LanceDB schema. Implemented by
    `RemoteOpenAICompat`.
  - `mock`  (sandbox / CI) — deterministic hash-based pseudo-embeddings;
    bypasses Hugging Face entirely so the retrieval plumbing can be tested
    in environments without HF access. Implemented by `MockEmbed`.

The mock backend is NOT semantic — it embeds by token hashing — so it won't
retrieve meaningfully. It's purely for verifying the LanceDB hybrid wiring,
RRF fusion, and reranker integration end-to-end without weights.

Public surface: the module-level functions `embed_passages`, `embed_query`,
`embed_with_colbert`, and `warm` delegate to the env-selected `EmbedBackend`.
They remain the stable import points for the rest of the codebase.
"""

from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np

EMBED_DIM = 1024
MODEL_NAME = "BAAI/bge-m3"

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _backend_name() -> str:
    """Resolve the configured backend name, normalizing the `bge-m3` alias.

    `bge-m3` is kept as a synonym for `local` for backward compatibility with
    deployments (and the reranker) that key off the historical default.
    """
    name = os.environ.get("KLERK_EMBED_BACKEND", "local").strip().lower()
    if name in ("", "bge-m3", "bge"):
        return "local"
    return name


# ─── Backend protocol ───────────────────────────────────────────────────────
class EmbedBackend(ABC):
    """Abstract embedding backend.

    Concrete backends provide a dense head (used for indexing + query vectors)
    and, optionally, a ColBERT token-level head for late-interaction rerank.
    Backends with no ColBERT head must raise RuntimeError from
    `embed_with_colbert` so the reranker can fall back to RRF order.
    """

    name: str = "abstract"

    @abstractmethod
    def embed_passages(self, texts: list[str], *, batch_size: int = 12) -> np.ndarray:
        """Dense embeddings for indexing. Returns (N, 1024) float32, L2-normalized."""

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """Dense embedding for one query. Returns (1024,) float32, L2-normalized."""

    @abstractmethod
    def embed_with_colbert(self, texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
        """Token-level ColBERT vectors. Raises RuntimeError if unsupported."""

    @abstractmethod
    def warm(self) -> str:
        """Eagerly load / validate the backend; return a short status string."""


# ─── Local BGE-M3 backend ─────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _bge_model():
    """Singleton BGEM3FlagModel — shared between embed and rerank paths."""
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "local embed backend requires the 'local' extra "
            "(FlagEmbedding, torch, transformers). Install with "
            "`pip install klerk[local]` (or `klerk[full]`), or set "
            "KLERK_EMBED_BACKEND=remote / =mock to avoid local weights."
        ) from exc

    device = os.environ.get("KLERK_EMBED_DEVICE", "cpu")
    use_fp16 = device.startswith("cuda")
    return BGEM3FlagModel(MODEL_NAME, devices=[device], use_fp16=use_fp16)


class LocalBGE(EmbedBackend):
    """BGE-M3 via FlagEmbedding — dense + ColBERT from one local model load."""

    name = "local"

    def embed_passages(self, texts: list[str], *, batch_size: int = 12) -> np.ndarray:
        out = _bge_model().encode(
            texts,
            batch_size=batch_size,
            max_length=8192,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return np.asarray(out["dense_vecs"], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        out = _bge_model().encode(
            [text],
            max_length=8192,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return np.asarray(out["dense_vecs"][0], dtype=np.float32)

    def embed_with_colbert(self, texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
        out = _bge_model().encode(
            texts,
            batch_size=batch_size,
            max_length=8192,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )
        return [np.asarray(v, dtype=np.float32) for v in out["colbert_vecs"]]

    def warm(self) -> str:
        _bge_model()
        return MODEL_NAME


# ─── Remote OpenAI-compatible backend ─────────────────────────────────────────
def _remote_config() -> tuple[str, str, str]:
    """Resolve (endpoint, api_key, model) for the remote backend or fail clearly."""
    url = os.environ.get("KLERK_EMBED_REMOTE_URL", "").strip()
    key = os.environ.get("KLERK_EMBED_REMOTE_KEY", "").strip()
    model = os.environ.get("KLERK_EMBED_REMOTE_MODEL", "").strip()
    missing = [
        name
        for name, value in (
            ("KLERK_EMBED_REMOTE_URL", url),
            ("KLERK_EMBED_REMOTE_KEY", key),
            ("KLERK_EMBED_REMOTE_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "remote embed backend requires " + ", ".join(missing) + " (see .env.example)"
        )
    # Accept either a base URL or a full /embeddings URL.
    endpoint = url.rstrip("/")
    if not endpoint.endswith("/embeddings"):
        endpoint = f"{endpoint}/embeddings"
    return endpoint, key, model


class RemoteOpenAICompat(EmbedBackend):
    """Dense-only embeddings via an OpenAI-compatible `/embeddings` endpoint."""

    name = "remote"

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Returns (N, 1024) float32, L2-normalized to match the BGE-M3 contract.

        Raises RuntimeError if the provider returns a non-1024-d vector (the
        LanceDB schema is pinned to EMBED_DIM).
        """
        import httpx

        endpoint, key, model = _remote_config()
        resp = httpx.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": texts},
            timeout=60.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = sorted(payload["data"], key=lambda d: d.get("index", 0))
        vecs = np.asarray([row["embedding"] for row in rows], dtype=np.float32)
        if vecs.ndim != 2 or vecs.shape[1] != EMBED_DIM:
            got = vecs.shape[1] if vecs.ndim == 2 else vecs.shape
            raise RuntimeError(
                f"remote embed model '{model}' returned dim {got}, expected {EMBED_DIM}; "
                "set KLERK_EMBED_REMOTE_MODEL to a 1024-d model"
            )
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vecs / norms).astype(np.float32)

    def embed_passages(self, texts: list[str], *, batch_size: int = 12) -> np.ndarray:
        return self._embed(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text])[0]

    def embed_with_colbert(self, texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
        raise RuntimeError("ColBERT vectors unavailable in remote mode")

    def warm(self) -> str:
        # No local weights to load; validate config eagerly so misconfig fails
        # at startup rather than on first query.
        _, _, model = _remote_config()
        return f"remote:{model}"


# ─── HuggingFace Inference (feature-extraction) backend ───────────────────────
def _hf_config() -> tuple[str, str, str]:
    """Resolve (url, api_key, model) for the HF feature-extraction backend.

    Auth falls back to the standard HF token envs, so a deployment that already
    set HF_TOKEN (for model downloads) gets remote embeddings for free.
    """
    model = os.environ.get("KLERK_EMBED_HF_MODEL", MODEL_NAME).strip() or MODEL_NAME
    key = (
        os.environ.get("KLERK_EMBED_HF_KEY")
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or ""
    ).strip()
    url = os.environ.get("KLERK_EMBED_HF_URL", "").strip() or (
        f"https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"
    )
    if not key:
        raise RuntimeError(
            "hf embed backend requires an HF token — set HF_TOKEN (or "
            "KLERK_EMBED_HF_KEY). See .env.example."
        )
    return url, key, model


class HFInference(EmbedBackend):
    """Dense embeddings via HuggingFace Inference *feature-extraction*.

    HF doesn't speak the OpenAI `/embeddings` shape; it returns the raw
    feature-extraction output, which is either ``[N, dim]`` sentence vectors
    (BGE-M3 is pooled) or ``[N, seq, dim]`` token vectors that we mean-pool.
    We normalize either into the (N, 1024) L2-normalized contract LanceDB
    expects. Reuses the HF token; ideal for the lite / phone path where HF is
    reachable but a 1.2GB local download isn't. Dense-only — no ColBERT head,
    so the reranker falls back to RRF order.
    """

    name = "hf"

    def _embed(self, texts: list[str]) -> np.ndarray:
        import httpx

        url, key, model = _hf_config()
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"inputs": texts, "options": {"wait_for_model": True}},
            timeout=120.0,  # generous — HF may cold-start the model
        )
        resp.raise_for_status()
        arr = np.asarray(resp.json(), dtype=np.float32)
        # Normalize shape → (N, dim):
        #   (dim,)          single vector
        #   (N, dim)        sentence embeddings (BGE-M3 is pooled)
        #   (N, seq, dim)   token-level → mean-pool over the sequence axis
        if arr.ndim == 1:
            arr = arr[None, :]
        elif arr.ndim == 3:
            arr = arr.mean(axis=1)
        if arr.ndim != 2 or arr.shape[1] != EMBED_DIM:
            raise RuntimeError(
                f"HF model '{model}' returned shape {arr.shape}, expected (N, {EMBED_DIM}); "
                "check KLERK_EMBED_HF_MODEL / KLERK_EMBED_HF_URL"
            )
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (arr / norms).astype(np.float32)

    def embed_passages(self, texts: list[str], *, batch_size: int = 12) -> np.ndarray:
        # HF serverless caps payload size — chunk to stay under it.
        chunks = [self._embed(texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
        return (
            np.concatenate(chunks, axis=0)
            if chunks
            else np.zeros((0, EMBED_DIM), dtype=np.float32)
        )

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text])[0]

    def embed_with_colbert(self, texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
        raise RuntimeError("ColBERT vectors unavailable in HF inference mode")

    def warm(self) -> str:
        _, _, model = _hf_config()
        return f"hf:{model}"


# ─── Mock backend ─────────────────────────────────────────────────────────────
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


class MockEmbed(EmbedBackend):
    """Deterministic hash-based pseudo-embeddings for CI / sandbox."""

    name = "mock"

    def embed_passages(self, texts: list[str], *, batch_size: int = 12) -> np.ndarray:
        return np.stack([_mock_vector(t) for t in texts]).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return _mock_vector(text)

    def embed_with_colbert(self, texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
        return [_mock_vector(t).reshape(1, EMBED_DIM) for t in texts]

    def warm(self) -> str:
        return "mock"


# ─── Backend selection + module-level public API ──────────────────────────────
_BACKENDS: dict[str, type[EmbedBackend]] = {
    "local": LocalBGE,
    "remote": RemoteOpenAICompat,
    "hf": HFInference,
    "mock": MockEmbed,
}


def get_backend(name: str | None = None) -> EmbedBackend:
    """Instantiate the embed backend (env-selected unless `name` is given)."""
    resolved = name.strip().lower() if name else _backend_name()
    try:
        cls = _BACKENDS[resolved]
    except KeyError:
        raise RuntimeError(
            f"unknown KLERK_EMBED_BACKEND={resolved!r}; "
            f"expected one of: local, remote, hf, mock"
        ) from None
    return cls()


def embed_passages(texts: list[str], *, batch_size: int = 12) -> np.ndarray:
    """Dense embeddings for indexing. Returns (N, 1024) float32, L2-normalized."""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    return get_backend().embed_passages(texts, batch_size=batch_size)


def embed_query(text: str) -> np.ndarray:
    """Dense embedding for a single query. Returns (1024,) float32, L2-normalized."""
    return get_backend().embed_query(text)


def embed_with_colbert(texts: list[str], *, batch_size: int = 12) -> list[np.ndarray]:
    """Token-level ColBERT vectors for late-interaction reranking.

    Returns a list of length N; each element is a (n_tokens, 1024) float32
    ndarray, L2-normalized along the last axis. Token count varies by input.

    Mock backend returns single-row matrices derived from the mock dense
    vector so the MaxSim path stays exercisable in CI without weights.

    Remote backend has no ColBERT equivalent (OpenAI-compat `/embeddings`
    is dense-only), so it raises RuntimeError; the reranker catches this and
    falls back to RRF order.
    """
    if not texts:
        return []
    return get_backend().embed_with_colbert(texts, batch_size=batch_size)


def warm() -> str:
    return get_backend().warm()
