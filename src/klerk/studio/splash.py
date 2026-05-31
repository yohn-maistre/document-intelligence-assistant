"""Boot splash for klerk studio.

ASCII logo + a tools/skills inventory + a status footer. Mounted over the
dashboard at startup and auto-dismissed on the first key/click (Pi
convention) so the operator drops straight into the floor.
"""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Static

LOGO = r"""
 ██╗  ██╗██╗     ███████╗██████╗ ██╗  ██╗
 ██║ ██╔╝██║     ██╔════╝██╔══██╗██║ ██╔╝
 █████╔╝ ██║     █████╗  ██████╔╝█████╔╝
 ██╔═██╗ ██║     ██╔══╝  ██╔══██╗██╔═██╗
 ██║  ██╗███████╗███████╗██║  ██║██║  ██╗
 ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
"""

TOOLS = [
    "search_hybrid", "extract_actions", "draft_doc",
    "scan_conflicts", "ingest_path", "sync_drive",
]


class SplashScreen(ModalScreen[None]):
    """Modal splash; dismisses itself on first input."""

    DEFAULT_CSS = """
    SplashScreen {
        align: center middle;
        background: $background;
    }
    SplashScreen #logo {
        color: $primary;
        text-style: bold;
    }
    SplashScreen #inventory {
        color: $secondary;
        margin-top: 1;
    }
    SplashScreen #hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        tools = "  ".join(f"[b]{t}[/b]" for t in TOOLS)
        body = (
            f"{LOGO}\n"
            "[dim]document-intelligence assistant — Hermes-style agentic RAG[/dim]\n\n"
            f"[b]tools[/b]   {tools}\n"
            "[b]skills[/b]  hybrid retrieval · conflict scan · action items · "
            "doc-writer · KG · drive sync\n\n"
            "[b]status[/b]  engine: in-process (lite) · surfaces: terminal + textual-serve"
        )
        with Middle(), Center():
            yield Static(body, id="inventory", markup=True)
        with Center():
            yield Static("[dim]press any key to enter studio[/dim]", id="hint")

    def _dismiss(self) -> None:
        if self.is_running:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:  # noqa: ARG002
        self._dismiss()

    def on_mouse_down(self, event: events.MouseDown) -> None:  # noqa: ARG002
        self._dismiss()
