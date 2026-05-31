"""Traces pane — Phoenix link + last-span summary.

A button opens the local Phoenix UI in the operator's browser; the body
shows a best-effort summary of the most recent span persisted under
``.phoenix/`` (drift / ingest run JSONL stand in when Phoenix is absent).
"""

from __future__ import annotations

import contextlib
import os
import webbrowser
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static


def _phoenix_url() -> str:
    port = os.environ.get("PHOENIX_PORT", "6006")
    return os.environ.get("PHOENIX_URL", f"http://localhost:{port}")


def _last_span_summary() -> str:
    """Best-effort: count persisted Phoenix spans + last drift event."""
    lines: list[str] = []
    phoenix_db = os.environ.get("PHOENIX_WORKING_DIR", ".phoenix")
    spans = Path(phoenix_db)
    lines.append(
        f"phoenix store: {'present' if spans.exists() else 'not seeded — run a chat turn'}"
    )
    drift = Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "drift-events.jsonl"
    if drift.exists():
        try:
            tail = [ln for ln in drift.read_text().splitlines() if ln.strip()]
            lines.append(f"drift events: {len(tail)}")
        except OSError:
            pass
    return "\n".join(lines)


class TracesPanel(Container):
    """Phoenix link button + last-span summary."""

    DEFAULT_CSS = """
    TracesPanel {
        height: 1fr;
        border: round $secondary;
        border-title-color: $secondary;
        padding: 0 1;
    }
    TracesPanel Button {
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = "traces"
        yield Static(f"[b]Phoenix[/b]  {_phoenix_url()}")
        yield Button("open phoenix ↗", id="open-phoenix", variant="primary")
        yield Static(_last_span_summary(), id="span-summary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "open-phoenix":
            with contextlib.suppress(Exception):
                webbrowser.open(_phoenix_url())
