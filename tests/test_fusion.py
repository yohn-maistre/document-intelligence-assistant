"""Reciprocal Rank Fusion — correctness tests (no model deps)."""

from __future__ import annotations

from klerk.rag.fusion import reciprocal_rank_fusion, rrf_by_key


def test_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"]])
    items = [x for x, _ in fused]
    assert items == ["a", "b", "c"]


def test_doc_in_both_outranks_solo() -> None:
    # 'a' is #1 in list 1 and #1 in list 2 → must beat 'b' which is solo #1 of list 2
    fused = reciprocal_rank_fusion([["a", "x", "y"], ["a", "b", "c"]])
    items = [x for x, _ in fused]
    assert items[0] == "a"


def test_score_formula() -> None:
    # k=60, item 'a' at rank 1 in both lists: score = 1/61 + 1/61
    fused = dict(reciprocal_rank_fusion([["a"], ["a"]], k=60))
    assert abs(fused["a"] - (2 / 61)) < 1e-9


def test_rrf_by_key_ranks_tracked() -> None:
    list1 = [{"chunk_id": "a", "text": "..."}, {"chunk_id": "b", "text": "..."}]
    list2 = [{"chunk_id": "b", "text": "..."}, {"chunk_id": "c", "text": "..."}]
    fused = rrf_by_key([list1, list2], key="chunk_id", k=60)

    by_key = {k: (s, r) for k, s, r in fused}
    # 'b' appears in both → must rank first
    assert fused[0][0] == "b"
    # rank-tracking arrays
    assert by_key["a"][1] == [1, 0]   # rank 1 in list1, absent from list2
    assert by_key["b"][1] == [2, 1]   # rank 2 in list1, rank 1 in list2
    assert by_key["c"][1] == [0, 2]   # absent from list1, rank 2 in list2


def test_empty_inputs() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []


def test_k_smoothing_effect() -> None:
    # Larger k → smaller per-rank weight, less spread between ranks
    fused_small_k = dict(reciprocal_rank_fusion([["a", "b"]], k=1))
    fused_large_k = dict(reciprocal_rank_fusion([["a", "b"]], k=1000))
    spread_small = fused_small_k["a"] - fused_small_k["b"]
    spread_large = fused_large_k["a"] - fused_large_k["b"]
    assert spread_small > spread_large
