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
        color: $secondary;
        text-align: center;
    }
    SplashScreen #inventory {
        text-align: center;
        margin-top: 1;
        width: 64;
    }
    SplashScreen #hint {
        color: $text-muted;
        text-align: center;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        tools = "  ".join(f"[$secondary]{t}[/]" for t in TOOLS)
        body = (
            f"{LOGO}\n"
            "[b $accent]document intelligence agent[/]\n"
            "[dim]chat with your knowledge — grounded · cited · multilingual[/dim]\n\n"
            f"[dim]tools[/]    {tools}\n"
            "[dim]skills[/]   [$secondary]hybrid retrieval · conflict scan · action items · "
            "doc-writer · knowledge graph · drive sync[/]\n\n"
            "[dim]engine[/] in-process (lite)    [dim]surfaces[/] terminal · browser"
        )
        with Middle(), Center():
            yield Static(body, id="inventory", markup=True)
        with Center():
            yield Static("[dim]press any key to enter[/dim]", id="hint")

    def _dismiss(self) -> None:
        if self.is_running:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:  # noqa: ARG002
        self._dismiss()

    def on_mouse_down(self, event: events.MouseDown) -> None:  # noqa: ARG002
        self._dismiss()
