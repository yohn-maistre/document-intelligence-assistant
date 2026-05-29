"""Custom 5-axis evaluation rubric — runs over Q&A or proposal outputs.

This is the "differentiator beyond RAGAS" the design-decisions doc highlights.
Five axes, every score in [0, 1]:

  - retrieval_recall      : fraction of expected_chunks present in retrieval
  - substring_coverage    : fraction of expected_substrings present in answer
  - citation_grounded     : all cited chunk_ids exist in the retrieved set
  - locale_match          : answer's primary language matches the golden item's
  - confidence            : the model's own self-reported citation coverage

The mean is reported alongside per-axis scores. SEA-HELM-style Bahasa parity
is just "compute per locale, report the delta."
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from klerk.agent.crag import ask as crag_ask
from klerk.eval.golden import GoldenItem

CITATION_RE = re.compile(r"\[([a-zA-Z0-9_\-]+):(\d+)\]")
_ID_MARKERS = ("yang ", "dengan ", "untuk ", "tidak ", "adalah ", "pasal ", "kontrak", "kebijakan")
_EN_MARKERS = (" the ", " and ", " for ", " with ", " policy ", " consultant ", " employee ")


def _detect_locale(text: str) -> str:
    snippet = text.lower()[:4096]
    id_h = sum(snippet.count(m) for m in _ID_MARKERS)
    en_h = sum(snippet.count(m) for m in _EN_MARKERS)
    if id_h > en_h * 1.2:
        return "id"
    if en_h > id_h * 1.2:
        return "en"
    return "und"


@dataclass
class RubricItemResult:
    item_id: str
    locale: str
    retrieval_recall: float
    substring_coverage: float
    citation_grounded: float
    locale_match: float
    confidence: float
    answer: str
    citations: list[str]
    retrieved_chunk_ids: list[str]

    @property
    def mean(self) -> float:
        return (
            self.retrieval_recall
            + self.substring_coverage
            + self.citation_grounded
            + self.locale_match
            + self.confidence
        ) / 5.0


def _score_item(item: GoldenItem) -> RubricItemResult:
    trace = crag_ask(item.question, locale=item.locale, k_final=8)
    retrieved_ids = {
        c.chunk_id for round_ in trace.retrievals for c in round_
    } | {
        c.chunk_id for round_ in trace.corrections if round_ for c in round_
    }

    # Axis 1: retrieval recall (expected_chunks ∩ retrieved / expected)
    if item.expected_chunks:
        hits = sum(1 for cid in item.expected_chunks if cid in retrieved_ids)
        retrieval_recall = hits / len(item.expected_chunks)
    else:
        retrieval_recall = 1.0  # no expectation → not penalised

    # Axis 2: substring coverage
    answer_lower = trace.answer.answer.lower()
    if item.expected_substrings:
        sub_hits = sum(1 for s in item.expected_substrings if s.lower() in answer_lower)
        substring_coverage = sub_hits / len(item.expected_substrings)
    else:
        substring_coverage = 1.0

    # Axis 3: citation grounded — every cited id must be in retrieved set
    if trace.answer.citations:
        grounded = sum(1 for cid in trace.answer.citations if cid in retrieved_ids)
        citation_grounded = grounded / len(trace.answer.citations)
    else:
        citation_grounded = 0.0  # answer with no citations fails this axis

    # Axis 4: locale match (en/id; und → 0.5 partial credit)
    detected = _detect_locale(trace.answer.answer)
    if detected == item.locale:
        locale_match = 1.0
    elif detected == "und":
        locale_match = 0.5
    else:
        locale_match = 0.0

    # Axis 5: model self-reported confidence (capped at 1.0)
    confidence = min(1.0, max(0.0, trace.answer.confidence))

    return RubricItemResult(
        item_id=item.id,
        locale=item.locale,
        retrieval_recall=retrieval_recall,
        substring_coverage=substring_coverage,
        citation_grounded=citation_grounded,
        locale_match=locale_match,
        confidence=confidence,
        answer=trace.answer.answer,
        citations=list(trace.answer.citations),
        retrieved_chunk_ids=sorted(retrieved_ids),
    )


def run(items: list[GoldenItem]) -> list[RubricItemResult]:
    """Score each item; never raises on per-item failure (records 0s instead)."""
    out: list[RubricItemResult] = []
    for item in items:
        try:
            out.append(_score_item(item))
        except Exception as e:  # noqa: BLE001
            out.append(
                RubricItemResult(
                    item_id=item.id,
                    locale=item.locale,
                    retrieval_recall=0.0,
                    substring_coverage=0.0,
                    citation_grounded=0.0,
                    locale_match=0.0,
                    confidence=0.0,
                    answer=f"(ERROR: {type(e).__name__}: {e})",
                    citations=[],
                    retrieved_chunk_ids=[],
                )
            )
    return out


def aggregate(results: list[RubricItemResult]) -> dict[str, Any]:
    """Group by locale + overall; mean each axis."""
    if not results:
        return {"overall": {}, "by_locale": {}}

    def _mean(rows: list[RubricItemResult], attr: str) -> float:
        return sum(getattr(r, attr) for r in rows) / len(rows)

    def _summary(rows: list[RubricItemResult]) -> dict[str, float]:
        return {
            "n": len(rows),
            "retrieval_recall": _mean(rows, "retrieval_recall"),
            "substring_coverage": _mean(rows, "substring_coverage"),
            "citation_grounded": _mean(rows, "citation_grounded"),
            "locale_match": _mean(rows, "locale_match"),
            "confidence": _mean(rows, "confidence"),
            "mean": sum(r.mean for r in rows) / len(rows),
        }

    by_locale: dict[str, dict[str, float]] = {}
    locales = sorted({r.locale for r in results})
    for loc in locales:
        rows = [r for r in results if r.locale == loc]
        by_locale[loc] = _summary(rows)

    return {"overall": _summary(results), "by_locale": by_locale}
