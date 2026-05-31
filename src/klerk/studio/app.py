"""klerk studio — Bloomberg-style Textual dashboard (v7 Phase A.3).

A multi-pane operator cockpit over klerk's in-process engine and on-disk
artefacts. The floor (always ships) is five panes wired per v7 D6:

    ┌──────────────── status bar (model · drive · WIB · ctx) ────────────────┐
    │ files  │            live chat (in-process / SSE)            │ activity │
    │        │                                                    │ traces   │
    │        │                                                    │ [bonus]  │
    └────────┴────────────────────────────────────────────────────┴─────────┘

The right rail is a scrollable column: activity + traces (floor) followed by
the bonus panes (eval → kg → sparklines) when ``show_bonus`` is set. Each
bonus pane degrades to a hint when its data source is empty, so the floor is
never blocked by a missing eval run / KG / metrics.

Two run paths:

* ``run(...)``   — terminal TUI (also the ``klerk studio`` entry point).
* ``serve(...)`` — same app over the browser via ``textual-serve`` (guarded
  import; the dep lands in pyproject's ``server`` extra via session S5).

The full cockpit renders by default on any terminal width. ``--compact`` opts
into a chat-only layout for very cramped terminals. ("lite" elsewhere refers to
the backend — remote embeddings / in-process engine — never the UI.)
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, VerticalScroll
from textual.widget import Widget

from klerk.studio.splash import SplashScreen
from klerk.studio.theme import KLERK_THEME, STUDIO_CSS
from klerk.studio.widgets import (
    ActivityTable,
    FilesTree,
    LiveChat,
    StatusBar,
    TracesPanel,
)


def _bonus_widgets() -> list[Widget]:
    """Instantiate the bonus panes (eval → kg → sparklines), guarded.

    Each is best-effort and renders a hint when its data source is empty, so
    they are always safe to mount. Import failures are swallowed so a missing
    optional dependency never breaks the floor.
    """
    out: list[Widget] = []
    try:
        from klerk.studio.widgets.eval_panel import EvalPanel

        out.append(EvalPanel(id="eval-pane"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from klerk.studio.widgets.kg_snapshot import KgSnapshot

        out.append(KgSnapshot(id="kg-pane"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from klerk.studio.widgets.graph import SparkGraph

        out.append(SparkGraph(id="spark-pane"))
    except Exception:  # noqa: BLE001
        pass
    return out


class KlerkStudio(App):
    """The floor dashboard. Composes the five floor panes in a Grid."""

    CSS = (
        STUDIO_CSS
        + """
    #studio-grid {
        grid-size: 3 1;
        grid-columns: 28 1fr 34;
        grid-gutter: 0 0;
    }
    #right-rail { height: 1fr; }
    #right-rail > ActivityTable { height: 14; }
    #right-rail > TracesPanel { height: 9; }
    #right-rail > EvalPanel { height: 12; }
    #right-rail > KgSnapshot { height: 14; }
    #right-rail > SparkGraph { height: 16; }
    #lite-root { height: 1fr; }
    """
    )

    BINDINGS = [
        Binding("ctrl+q", "quit", "quit"),
        Binding("ctrl+r", "reload", "reload"),
        Binding("f1", "splash", "about"),
    ]

    TITLE = "klerk studio"
    SUB_TITLE = "document-intelligence cockpit"

    def __init__(
        self,
        *,
        mode: str = "lite",
        base_url: str = "http://localhost:8000",
        locale: str = "en",
        lite_layout: bool = False,
        show_splash: bool = True,
        show_bonus: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mode = mode
        self.base_url = base_url
        self.locale = locale
        self._force_lite_layout = lite_layout
        self._show_splash = show_splash
        self._show_bonus = show_bonus

    @property
    def _use_lite_layout(self) -> bool:
        # Full cockpit by default (on any terminal width); the compact,
        # chat-only layout is strictly opt-in via --compact. "lite" elsewhere
        # refers to the backend (remote embed / in-process engine), not the UI.
        return self._force_lite_layout

    def compose(self) -> ComposeResult:
        yield StatusBar(mode=self.mode, base_url=self.base_url, id="status-bar")
        if self._use_lite_layout:
            yield Container(
                LiveChat(
                    mode=self.mode,
                    base_url=self.base_url,
                    locale=self.locale,
                    id="chat-pane",
                ),
                id="lite-root",
            )
        else:
            with Grid(id="studio-grid"):
                yield FilesTree(id="files-pane")
                yield LiveChat(
                    mode=self.mode,
                    base_url=self.base_url,
                    locale=self.locale,
                    id="chat-pane",
                )
                with VerticalScroll(id="right-rail"):
                    yield ActivityTable(id="activity-pane")
                    yield TracesPanel(id="traces-pane")
                    if self._show_bonus:
                        yield from _bonus_widgets()

    def on_mount(self) -> None:
        self.register_theme(KLERK_THEME)
        self.theme = KLERK_THEME.name
        if self._show_splash:
            self.push_screen(SplashScreen())

    def action_reload(self) -> None:
        self.refresh(recompose=True)

    def action_splash(self) -> None:
        self.push_screen(SplashScreen())


# ─── Entry points ─────────────────────────────────────────────────────────────
def run(
    *,
    mode: str = "lite",
    base_url: str = "http://localhost:8000",
    locale: str = "en",
    compact: bool = False,
) -> None:
    """Run the terminal TUI (the ``klerk studio`` entry point)."""
    KlerkStudio(
        mode=mode, base_url=base_url, locale=locale, lite_layout=compact
    ).run()


def serve(
    *,
    host: str = "localhost",
    port: int = 8001,
    mode: str = "full",
    base_url: str = "http://localhost:8000",
) -> None:
    """Serve the studio in-browser via textual-serve (guarded import).

    The ``textual-serve`` dependency is added to pyproject's ``server`` extra
    by session S5; until then this raises an actionable RuntimeError so the
    terminal path keeps working without the dep installed.
    """
    try:
        from textual_serve.server import Server  # type: ignore[import-not-found]
    except ModuleNotFoundError as e:  # pragma: no cover — dep added by S5
        raise RuntimeError(
            "textual-serve is not installed. Install the server extra "
            "(`uv sync --extra server`) or `pip install textual-serve`."
        ) from e

    command = (
        f"python -m klerk.studio.app --served "
        f"--mode {mode} --base-url {base_url}"
    )
    Server(command, host=host, port=port).serve()


def main() -> None:
    """CLI shim for ``python -m klerk.studio.app`` and the served subprocess."""
    import argparse

    parser = argparse.ArgumentParser(prog="klerk-studio")
    parser.add_argument("--serve", action="store_true", help="serve in browser")
    parser.add_argument("--served", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--compact", action="store_true", help="chat-only layout")
    parser.add_argument("--mode", default="lite", choices=["lite", "full"])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--locale", default="en")
    args = parser.parse_args()

    if args.serve:
        serve(mode="full", base_url=args.base_url)
        return
    run(mode=args.mode, base_url=args.base_url, locale=args.locale, compact=args.compact)


if __name__ == "__main__":
    main()
