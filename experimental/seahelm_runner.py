"""SEA-HELM-style Bahasa parity report.

SEA-HELM (Singapore AI's Southeast Asia LM benchmark) is the canonical Bahasa
benchmark in May 2026. We don't reproduce it — we extract its *methodology*:

  - Score Bahasa Q&A and English Q&A independently using the same rubric.
  - Report the delta per axis. A small / zero delta means the system handles
    Bahasa as well as English; a large delta is an honest gap to flag.

This file is intentionally thin — it delegates scoring to `rubric.run` and
slices the results by locale.
"""

from __future__ import annotations

from typing import Any

from klerk.eval.golden import load
from klerk.eval.rubric import RubricItemResult, aggregate, run


def run_seahelm() -> dict[str, Any]:
    items = load()
    if not items:
        return {
            "available": False,
            "reason": "no golden items — drop YAML into data/golden/",
            "results": [],
            "aggregate": {},
        }

    results: list[RubricItemResult] = run(items)
    agg = aggregate(results)

    by_loc = agg.get("by_locale", {})
    delta: dict[str, float] = {}
    if "en" in by_loc and "id" in by_loc:
        for axis in (
            "retrieval_recall",
            "substring_coverage",
            "citation_grounded",
            "locale_match",
            "confidence",
            "mean",
        ):
            delta[axis] = by_loc["id"][axis] - by_loc["en"][axis]

    return {
        "available": True,
        "results": results,
        "aggregate": agg,
        "id_minus_en_delta": delta,
    }
