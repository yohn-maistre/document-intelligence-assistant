"""BGE-M3 ColBERT-head rerank sanity tests.

The real backend (`KLERK_RERANK_BACKEND=bge-m3`, the default in production)
requires the ~1.2GB BGE-M3 weights. CI uses the mock Jaccard backend to
exercise the reranker plumbing and the MaxSim primitive without weights.
"""

from __future__ import annotations

import numpy as np

from klerk.rag.rerank import RerankResult, _maxsim, rerank


def test_mock_rerank_orders_matching_passages_first(monkeypatch):
    monkeypatch.setenv("KLERK_RERANK_BACKEND", "mock")
    passages = [
        {"chunk_id": "c1", "text": "the quick brown fox jumps over the lazy dog"},
        {"chunk_id": "c2", "text": "leave management policy effective 2025"},
        {"chunk_id": "c3", "text": "quick brown foxes are common in this region"},
    ]
    results = rerank("brown fox", passages, top_k=3)
    assert all(isinstance(r, RerankResult) for r in results)
    assert results[0].chunk_id in {"c1", "c3"}
    assert results[-1].chunk_id == "c2"


def test_rerank_empty_returns_empty():
    assert rerank("anything", []) == []


def test_rerank_top_k_truncates(monkeypatch):
    monkeypatch.setenv("KLERK_RERANK_BACKEND", "mock")
    passages = [{"chunk_id": f"c{i}", "text": f"document number {i}"} for i in range(10)]
    results = rerank("document", passages, top_k=3)
    assert len(results) == 3


def test_rerank_preserves_original_rank(monkeypatch):
    monkeypatch.setenv("KLERK_RERANK_BACKEND", "mock")
    passages = [
        {"chunk_id": "a", "text": "no match here"},
        {"chunk_id": "b", "text": "perfect overlap match"},
        {"chunk_id": "c", "text": "also no match"},
    ]
    results = rerank("perfect overlap match", passages)
    by_id = {r.chunk_id: r for r in results}
    assert by_id["a"].original_rank == 1
    assert by_id["b"].original_rank == 2
    assert by_id["c"].original_rank == 3


def test_maxsim_orthogonal_pair_scores_zero():
    q = np.array([[1.0, 0.0]], dtype=np.float32)
    p = np.array([[0.0, 1.0]], dtype=np.float32)
    assert _maxsim(q, p) == 0.0


def test_maxsim_matching_query_scores_one_per_token():
    q = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    p = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    # Each of the 2 query tokens finds its perfect cosine match → MaxSim = 2.0
    assert _maxsim(q, p) == 2.0


def test_maxsim_empty_inputs_score_zero():
    empty = np.zeros((0, 4), dtype=np.float32)
    p = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    assert _maxsim(empty, p) == 0.0
    assert _maxsim(p, empty) == 0.0
