"""Remote embed backend (`KLERK_EMBED_BACKEND=remote`).

Exercises the provider-neutral OpenAI-compatible `/embeddings` path with a
mocked httpx so no network or weights are needed:

  - routing: embed_passages / embed_query hit the remote endpoint
  - request contract: Bearer auth, model + input JSON, `/embeddings` suffix
  - dim contract: non-1024-d responses fail clearly
  - config validation: missing env vars fail clearly
  - ColBERT error path: unavailable in remote mode
  - rerank graceful fallback: RRF order preserved when ColBERT raises
"""

from __future__ import annotations

import httpx
import numpy as np
import pytest

from klerk.rag import embed, rerank

EMBED_DIM = embed.EMBED_DIM


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def _embedding_payload(vectors: list[list[float]]) -> dict:
    return {"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]}


@pytest.fixture
def remote_env(monkeypatch):
    monkeypatch.setenv("KLERK_EMBED_BACKEND", "remote")
    monkeypatch.setenv("KLERK_EMBED_REMOTE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("KLERK_EMBED_REMOTE_KEY", "sk-test-123")
    monkeypatch.setenv("KLERK_EMBED_REMOTE_MODEL", "test-embed-1024")


def _patch_post(monkeypatch, vectors: list[list[float]]):
    """Patch httpx.post to capture the request and return `vectors`."""
    captured: dict = {}

    def fake_post(url, *, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(_embedding_payload(vectors))

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


def test_embed_passages_routes_to_remote(remote_env, monkeypatch):
    vecs = [[1.0] * EMBED_DIM, [2.0] * EMBED_DIM]
    captured = _patch_post(monkeypatch, vecs)

    out = embed.embed_passages(["hello", "world"])

    assert out.shape == (2, EMBED_DIM)
    assert out.dtype == np.float32
    # rows L2-normalized
    np.testing.assert_allclose(np.linalg.norm(out, axis=1), [1.0, 1.0], rtol=1e-5)
    # request contract
    assert captured["url"].endswith("/embeddings")
    assert captured["headers"]["Authorization"] == "Bearer sk-test-123"
    assert captured["json"] == {"model": "test-embed-1024", "input": ["hello", "world"]}


def test_embed_query_routes_to_remote(remote_env, monkeypatch):
    _patch_post(monkeypatch, [[3.0] * EMBED_DIM])
    out = embed.embed_query("a query")
    assert out.shape == (EMBED_DIM,)
    np.testing.assert_allclose(np.linalg.norm(out), 1.0, rtol=1e-5)


def test_endpoint_suffix_not_doubled(remote_env, monkeypatch):
    monkeypatch.setenv("KLERK_EMBED_REMOTE_URL", "https://api.example.com/v1/embeddings")
    captured = _patch_post(monkeypatch, [[1.0] * EMBED_DIM])
    embed.embed_query("x")
    assert captured["url"] == "https://api.example.com/v1/embeddings"


def test_dim_mismatch_raises(remote_env, monkeypatch):
    _patch_post(monkeypatch, [[1.0] * 512])
    with pytest.raises(RuntimeError, match="dim 512"):
        embed.embed_passages(["oops"])


def test_missing_config_raises(monkeypatch):
    monkeypatch.setenv("KLERK_EMBED_BACKEND", "remote")
    monkeypatch.delenv("KLERK_EMBED_REMOTE_URL", raising=False)
    monkeypatch.delenv("KLERK_EMBED_REMOTE_KEY", raising=False)
    monkeypatch.delenv("KLERK_EMBED_REMOTE_MODEL", raising=False)
    with pytest.raises(RuntimeError) as exc:
        embed.embed_query("x")
    msg = str(exc.value)
    assert "KLERK_EMBED_REMOTE_URL" in msg
    assert "KLERK_EMBED_REMOTE_KEY" in msg
    assert "KLERK_EMBED_REMOTE_MODEL" in msg


def test_colbert_unavailable_in_remote_mode(remote_env):
    with pytest.raises(RuntimeError, match="ColBERT vectors unavailable in remote mode"):
        embed.embed_with_colbert(["text"])


def test_warm_validates_config_without_network(remote_env):
    assert embed.warm() == "remote:test-embed-1024"


def test_rerank_falls_back_to_rrf_order(remote_env):
    passages = [
        {"chunk_id": "a", "text": "first passage"},
        {"chunk_id": "b", "text": "second passage"},
        {"chunk_id": "c", "text": "third passage"},
    ]
    results = rerank.rerank("query", passages)
    # ColBERT unavailable → input (RRF fusion) order is preserved
    assert [r.chunk_id for r in results] == ["a", "b", "c"]
    assert [r.original_rank for r in results] == [1, 2, 3]
    # scores strictly descending so any downstream sort keeps the order
    assert results[0].score > results[1].score > results[2].score


def test_rerank_fallback_respects_top_k(remote_env):
    passages = [{"chunk_id": str(i), "text": f"p{i}"} for i in range(5)]
    results = rerank.rerank("query", passages, top_k=2)
    assert [r.chunk_id for r in results] == ["0", "1"]
