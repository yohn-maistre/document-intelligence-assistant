"""BONUS pane — 5-axis rubric + RAGAS row from the latest eval run.

Reads ``data/output/eval/{rubric,ragas}.json`` (the shape written by
``klerk eval run``), or the newest ``.klerk/eval-runs/<latest>.json`` if that
convention is used instead. Renders the five rubric axes + mean and a single
RAGAS row in a DataTable. Best-effort: an absent / unparseable run renders a
hint rather than raising.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

_AXES = (
    "retrieval_recall",
    "substring_coverage",
    "citation_grounded",
    "locale_match",
    "confidence",
    "mean",
)


def _state_dir() -> Path:
    return Path(os.environ.get("KLERK_STATE_DIR", ".klerk"))


def _load_eval() -> dict[str, Any]:
    """Prefer .klerk/eval-runs/<latest>.json; fall back to data/output/eval/."""
    runs = _state_dir() / "eval-runs"
    if runs.exists():
        files = sorted(runs.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            try:
                return json.loads(files[0].read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    out: dict[str, Any] = {}
    for name in ("rubric", "ragas"):
        p = Path(f"data/output/eval/{name}.json")
        if p.exists():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return out


class EvalPanel(Container):
    """5-axis rubric + RAGAS summary table."""

    DEFAULT_CSS = """
    EvalPanel {
        height: 1fr;
        border: solid $secondary;
        border-title-color: $secondary;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = "eval"
        blob = _load_eval()
        overall = (
            blob.get("rubric", {}).get("aggregate", {}).get("overall", {})
            if "rubric" in blob
            else blob.get("aggregate", {}).get("overall", {})
        )
        ragas = blob.get("ragas", {}).get("aggregate", {})

        if not overall and not ragas:
            yield Static(
                "[dim]No eval run yet — run [cyan]klerk eval run[/cyan].[/dim]"
            )
            return

        table: DataTable[str] = DataTable(cursor_type="row", zebra_stripes=True)
        table.add_columns("metric", "score")
        for axis in _AXES:
            if axis in overall:
                table.add_row(axis, f"{overall[axis]:.2f}")
        for k, v in ragas.items():
            try:
                table.add_row(f"ragas/{k}", f"{float(v):.2f}")
            except (TypeError, ValueError):
                continue
        yield table
