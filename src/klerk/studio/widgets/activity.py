"""Activity pane — a DataTable tailing ``.klerk/activity-log.jsonl``.

Each line is a tool-call record written by ``klerk.agent.tools._log_activity``:
``{ts, session_id, tool, display_name, status, duration_ms, summary}``.
Polls the file on an interval and re-renders when it grows.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

_POLL_SECONDS = 3.0
_TAIL = 200


def _activity_path() -> Path:
    return Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "activity-log.jsonl"


def _read_records(limit: int = _TAIL) -> list[dict[str, Any]]:
    p = _activity_path()
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


class ActivityTable(Container):
    """Live tail of tool-call activity."""

    DEFAULT_CSS = """
    ActivityTable {
        height: 1fr;
        border: round $secondary;
        border-title-color: $secondary;
    }
    ActivityTable DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = "activity"
        table: DataTable[str] = DataTable(
            id="activity-table", cursor_type="row", zebra_stripes=True
        )
        table.add_columns("time", "tool", "status", "ms", "summary")
        yield table
        yield Static("", id="activity-empty")

    def on_mount(self) -> None:
        self._last_mtime = 0.0
        self._refresh()
        self.set_interval(_POLL_SECONDS, self._refresh)

    def _refresh(self) -> None:
        p = _activity_path()
        mtime = p.stat().st_mtime if p.exists() else 0.0
        if mtime == self._last_mtime:
            return
        self._last_mtime = mtime
        records = _read_records()
        table = self.query_one("#activity-table", DataTable)
        table.clear()
        for rec in records:
            ts = rec.get("ts")
            when = (
                datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                if isinstance(ts, int | float)
                else "?"
            )
            status = rec.get("status", "?")
            mark = {"ok": "✓", "error": "✗"}.get(status, "·")
            summary = (rec.get("summary") or "").replace("\n", " ")[:60]
            table.add_row(
                when,
                rec.get("display_name") or rec.get("tool", "?"),
                f"{mark} {status}",
                str(rec.get("duration_ms", "")),
                summary,
            )
        empty = self.query_one("#activity-empty", Static)
        empty.update(
            "" if records else "[dim]no tool activity yet — run a chat turn or a verb[/dim]"
        )

    # Exposed for tests / manual refresh.
    def reload(self) -> None:
        self._last_mtime = -1.0
        self._refresh()
