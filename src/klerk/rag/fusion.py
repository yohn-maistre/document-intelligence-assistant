"""Reciprocal Rank Fusion (RRF) — hand-rolled, not imported.

Given multiple ranked result lists (bm25, vector, ...), combine them into a
single ranking using RRF:

    score(d) = Σ_i  1 / (k + rank_i(d))

where rank_i is the 1-indexed position of doc `d` in list `i`, and `k` is the
smoothing constant (k=60 is the published default and the one we use).

We hand-roll this rather than importing from a fusion library because (a) it's
~15 LOC, (b) the design-decisions doc cites this as one of our "no framework
worship" extracts, and (c) it lets us trivially log per-source contributions
for the Studio Trace panel.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    ranked_lists: Iterable[list[T]],
    *,
    k: int = 60,
) -> list[tuple[T, float]]:
    """Fuse multiple ranked lists into one. Returns (item, score) sorted desc.

    Items not appearing in a list contribute zero from that list.
    Equality of items is by `==` / hashable identity.
    """
    scores: dict[T, float] = {}
    for ranking in ranked_lists:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def rrf_by_key(
    ranked_lists: Iterable[list[dict]],
    *,
    key: str = "chunk_id",
    k: int = 60,
) -> list[tuple[str, float, list[int]]]:
    """RRF over lists of dicts, fusing by a chosen key field.

    Returns triples of `(key, fused_score, per_list_ranks)` where
    `per_list_ranks[i]` is the 1-indexed rank in list i (0 if absent).
    Useful for surfacing "vector ranked this #1, BM25 ranked this #5" in
    the Studio Trace panel.
    """
    lists = list(ranked_lists)
    scores: dict[str, float] = {}
    ranks: dict[str, list[int]] = {}
    for i, ranking in enumerate(lists):
        for rank, row in enumerate(ranking, start=1):
            key_val = row[key]
            scores[key_val] = scores.get(key_val, 0.0) + 1.0 / (k + rank)
            if key_val not in ranks:
                ranks[key_val] = [0] * len(lists)
            ranks[key_val][i] = rank

    fused = [(kv, scores[kv], ranks[kv]) for kv in scores]
    fused.sort(key=lambda t: t[1], reverse=True)
    return fused
