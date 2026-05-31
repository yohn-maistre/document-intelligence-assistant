"""BONUS pane — three stacked sparklines over recent activity.

Derives series from ``.klerk/activity-log.jsonl``:

* **latency p95** — rolling p95 of tool ``duration_ms`` over time buckets,
* **tools / minute** — tool-call count per minute bucket,

plus a flat **eval rubric mean** series from the latest eval run (a single
value broadcast to a short line so the axis renders even with one run).

Every series is best-effort and degrades to a flat zero line when no data is
present, so the pane always composes.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Sparkline, Static

_BUCKETS = 24  # ~24 time buckets across the tail window


def _state_dir() -> Path:
    return Path(os.environ.get("KLERK_STATE_DIR", ".klerk"))


def _activity_records(limit: int = 500) -> list[dict[str, Any]]:
    p = _state_dir() / "activity-log.jsonl"
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
            if line.strip():
                out.append(json.loads(line))
    except (OSError, ValueError):
        return []
    return out


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def _series() -> tuple[list[float], list[float], list[float]]:
    """Return (latency_p95, tools_per_minute, rubric_mean) series."""
    records = _activity_records()
    if not records:
        return [0.0], [0.0], _rubric_series()

    ts = [r.get("ts", 0.0) for r in records if isinstance(r.get("ts"), int | float)]
    if not ts:
        return [0.0], [0.0], _rubric_series()
    lo, hi = min(ts), max(ts)
    span = max(hi - lo, 1.0)

    lat_buckets: dict[int, list[float]] = defaultdict(list)
    count_buckets: dict[int, int] = defaultdict(int)
    for r in records:
        t = r.get("ts")
        if not isinstance(t, int | float):
            continue
        b = min(_BUCKETS - 1, int((t - lo) / span * (_BUCKETS - 1)))
        d = r.get("duration_ms")
        if isinstance(d, int | float):
            lat_buckets[b].append(float(d))
        count_buckets[b] += 1

    latency = [_p95(lat_buckets.get(i, [])) for i in range(_BUCKETS)]
    # tools/minute: scale per-bucket count by buckets-per-minute.
    bucket_seconds = span / _BUCKETS
    per_min = max(bucket_seconds, 1.0) / 60.0
    tools_per_min = [count_buckets.get(i, 0) / per_min for i in range(_BUCKETS)]
    return latency, tools_per_min, _rubric_series()


def _rubric_series() -> list[float]:
    p = Path("data/output/eval/rubric.json")
    if not p.exists():
        return [0.0]
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
        mean = blob.get("aggregate", {}).get("overall", {}).get("mean")
        if isinstance(mean, int | float):
            return [float(mean)] * 8
    except (OSError, ValueError):
        pass
    return [0.0]


class SparkGraph(Container):
    """Three stacked sparklines: latency p95 / tools-per-minute / rubric mean."""

    DEFAULT_CSS = """
    SparkGraph {
        height: 1fr;
        border: round $secondary;
        border-title-color: $secondary;
        padding: 0 1;
    }
    SparkGraph Sparkline {
        height: 3;
        margin-bottom: 1;
    }
    SparkGraph .spark-label {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = "metrics"
        latency, tools, rubric = _series()
        yield Static("latency p95 (ms)", classes="spark-label")
        yield Sparkline(latency, summary_function=max)
        yield Static("tools / minute", classes="spark-label")
        yield Sparkline(tools, summary_function=max)
        yield Static("eval rubric mean", classes="spark-label")
        yield Sparkline(rubric, summary_function=max)
