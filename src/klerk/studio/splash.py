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

# Solid full-block glyphs (no thin box-drawing outline) — renders clean and
# legible on mobile terminals where the ╔═╗ shadow font looked jagged. 23 cols
# wide so it never clips on a ~50-col phone screen.
LOGO = r"""
█  █  █    ███  ██   █  █
█ █   █    █    █ █  █ █
██    █    ██   ██   ██
█ █   █    █    █ █  █ █
█  █  ███  ███  █ █  █  █
"""

# One consolidated capability line — tools and skills overlapped (search_hybrid
# ≈ hybrid retrieval, scan_conflicts ≈ conflict scan, etc.), so collapse to the
# six things klerk actually does, named once.
CAPABILITIES = [
    "hybrid retrieval",
    "action items",
    "doc drafting",
    "conflict scan",
    "knowledge graph",
    "drive sync",
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
        width: auto;
        max-width: 100%;
    }
    SplashScreen #hint {
        color: $text-muted;
        text-align: center;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        # Two capability rows of three so nothing clips on a narrow phone.
        row1 = "  ·  ".join(f"[$secondary]{c}[/]" for c in CAPABILITIES[:3])
        row2 = "  ·  ".join(f"[$secondary]{c}[/]" for c in CAPABILITIES[3:])
        body = (
            f"{LOGO}\n"
            "[b $accent]document intelligence agent[/]\n"
            "[dim]grounded · cited · multilingual[/dim]\n\n"
            f"{row1}\n{row2}\n\n"
            "[dim]engine[/] in-process (lite)\n"
            "[dim]surfaces[/] terminal · browser"
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
