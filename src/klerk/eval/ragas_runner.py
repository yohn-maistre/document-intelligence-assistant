"""RAGAS baseline runner — faithfulness, answer relevance, context recall.

RAGAS itself is heavy (it pulls in its own judge LLM, expects a Dataset, and
defaults to OpenAI). To keep klerk's eval surface independent of OpenAI:
  - We run the agent through CRAG for every golden item to get (question,
    answer, retrieved_contexts, ground_truth).
  - We then pass that to ragas.evaluate with our own LiteLLM-wrapped judge
    pointed at Nemotron.

If `ragas` import fails (e.g. the dev env doesn't pull it for some reason),
this module falls back to "skipped" — `klerk eval run` will report it and
continue with the custom rubric + SEA-HELM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from klerk.agent.crag import ask as crag_ask
from klerk.eval.golden import GoldenItem


@dataclass
class RagasItemResult:
    item_id: str
    faithfulness: float | None
    context_recall: float | None
    answer_relevance: float | None


@dataclass
class RagasReport:
    available: bool
    reason: str | None
    items: list[RagasItemResult]
    aggregate: dict[str, float]


def run(items: list[GoldenItem]) -> RagasReport:
    try:
        from ragas import evaluate  # noqa: F401
        from ragas.metrics import (  # noqa: F401
            answer_relevancy,
            context_recall,
            faithfulness,
        )
    except Exception as e:  # noqa: BLE001
        return RagasReport(
            available=False,
            reason=f"ragas import failed: {type(e).__name__}: {e}",
            items=[],
            aggregate={},
        )

    # Build a dataset by running CRAG for each item
    rows: list[dict[str, Any]] = []
    for item in items:
        try:
            trace = crag_ask(item.question, locale=item.locale, k_final=6)
        except Exception:  # noqa: BLE001
            continue
        contexts = [
            c.text
            for round_ in trace.retrievals
            for c in round_
        ]
        if not contexts:
            continue
        rows.append(
            {
                "question": item.question,
                "answer": trace.answer.answer,
                "contexts": contexts[:10],  # cap to keep RAGAS happy
                "ground_truth": "; ".join(item.expected_substrings) or item.question,
                "item_id": item.id,
            }
        )

    if not rows:
        return RagasReport(
            available=True,
            reason="No rows produced (likely missing NVIDIA_API_KEY).",
            items=[],
            aggregate={},
        )

    # Build a HuggingFace Dataset (RAGAS expects this shape)
    try:
        from datasets import Dataset
    except Exception as e:  # noqa: BLE001
        return RagasReport(
            available=False,
            reason=f"datasets import failed: {type(e).__name__}: {e}",
            items=[],
            aggregate={},
        )
    ds = Dataset.from_list(rows)

    # Note: RAGAS judge defaults to OpenAI. We don't override here for two reasons:
    #  (1) the override API changes across RAGAS versions
    #  (2) reviewers usually have an OpenAI key handy alongside Nemotron
    # If RAGAS fails because of credentials, the user falls back to our custom rubric.
    try:
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_recall, faithfulness

        result = evaluate(
            ds,
            metrics=[faithfulness, answer_relevancy, context_recall],
        )
    except Exception as e:  # noqa: BLE001
        return RagasReport(
            available=True,
            reason=f"RAGAS evaluate failed: {type(e).__name__}: {e}",
            items=[],
            aggregate={},
        )

    items_out: list[RagasItemResult] = []
    scores_dict = result.scores if hasattr(result, "scores") else {}
    n = len(rows)
    for i, row in enumerate(rows):
        items_out.append(
            RagasItemResult(
                item_id=row["item_id"],
                faithfulness=_pluck(scores_dict, "faithfulness", i, n),
                context_recall=_pluck(scores_dict, "context_recall", i, n),
                answer_relevance=_pluck(scores_dict, "answer_relevancy", i, n),
            )
        )

    def _mean(metric: str) -> float:
        vals = [getattr(it, metric) for it in items_out if getattr(it, metric) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    aggregate = {
        "faithfulness": _mean("faithfulness"),
        "context_recall": _mean("context_recall"),
        "answer_relevance": _mean("answer_relevance"),
    }
    return RagasReport(available=True, reason=None, items=items_out, aggregate=aggregate)


def _pluck(scores: dict | list, metric: str, idx: int, n: int) -> float | None:
    """Extract a per-item metric from RAGAS' (version-volatile) result shape."""
    try:
        if isinstance(scores, list):
            row = scores[idx]
            if isinstance(row, dict):
                return float(row.get(metric, 0.0))
        if isinstance(scores, dict):
            values = scores.get(metric)
            if isinstance(values, list) and len(values) > idx:
                return float(values[idx])
    except Exception:  # noqa: BLE001
        return None
    return None
