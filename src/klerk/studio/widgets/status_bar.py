"""Top status bar — model · Drive sync · WIB clock · ctx tokens.

In **full** mode it polls ``{base_url}/health`` (and ``/sync-status``) every
5 seconds. In **lite** mode there is no HTTP surface, so it reports the
in-process model name from ``NemotronConfig`` and a static sync hint. The WIB
(Asia/Jakarta) clock ticks every second regardless of mode.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

_WIB = ZoneInfo("Asia/Jakarta")
_HEALTH_SECONDS = 5.0


class StatusBar(Horizontal):
    """Single-row dashboard header polling health on an interval."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: top;
        background: $panel;
        color: $foreground;
    }
    StatusBar Static {
        width: 1fr;
        content-align: center middle;
    }
    StatusBar #status-model { color: $primary; text-style: bold; }
    StatusBar #status-sync { color: $secondary; }
    StatusBar #status-ctx { color: $text-muted; }
    StatusBar #status-clock { color: $secondary; text-style: bold; }
    """

    def __init__(
        self,
        *,
        mode: str = "lite",
        base_url: str = "http://localhost:8000",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mode = mode
        self.base_url = base_url.rstrip("/")
        self._ctx_tokens = 0

    def compose(self) -> ComposeResult:
        yield Static("model: …", id="status-model")
        yield Static("drive: …", id="status-sync")
        yield Static("ctx: 0 tok", id="status-ctx")
        yield Static("--:--:-- WIB", id="status-clock")

    def on_mount(self) -> None:
        self._tick_clock()
        self.set_interval(1.0, self._tick_clock)
        self._poll_health()
        self.set_interval(_HEALTH_SECONDS, self._poll_health)

    def _tick_clock(self) -> None:
        now = datetime.now(_WIB).strftime("%H:%M:%S")
        self.query_one("#status-clock", Static).update(f"{now} WIB")

    def set_ctx_tokens(self, n: int) -> None:
        self._ctx_tokens = n
        self.query_one("#status-ctx", Static).update(f"ctx: {n} tok")

    def _poll_health(self) -> None:
        if self.mode == "full":
            self._poll_health_http()
        else:
            self._poll_health_lite()

    def _poll_health_lite(self) -> None:
        model = "(unconfigured)"
        try:
            from klerk.llm.nemotron import NemotronConfig

            model = NemotronConfig.from_env().model
        except Exception:  # noqa: BLE001
            pass
        self.query_one("#status-model", Static).update(f"model: {model}")
        self.query_one("#status-sync", Static).update("drive: in-process")

    def _poll_health_http(self) -> None:
        try:
            import httpx

            r = httpx.get(f"{self.base_url}/health", timeout=4)
            data = r.json()
            checks = data.get("checks", {})
            model_state = checks.get("nemotron_proxy", "?")
            drive_state = checks.get("drive", "?")
            self.query_one("#status-model", Static).update(
                f"model: nemotron [{model_state}] · {data.get('status', '?')}"
            )
            self.query_one("#status-sync", Static).update(f"drive: {drive_state}")
        except Exception as e:  # noqa: BLE001
            self.query_one("#status-model", Static).update("model: [unreachable]")
            self.query_one("#status-sync", Static).update(f"drive: {type(e).__name__}")
