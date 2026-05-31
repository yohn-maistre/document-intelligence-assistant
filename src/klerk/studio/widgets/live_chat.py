"""Live chat pane — drives one chat turn and streams events into a log.

Two modes:

* **LITE** (default): instantiates the in-process orchestrator
  (``klerk.agent.orchestrator.arun``) and consumes its async event stream
  directly — no HTTP, no second model load (v7 D1).
* **FULL**: opens an SSE connection to ``{base_url}/chat`` and parses the
  same event vocabulary (``session`` / ``tool_call`` / ``tool_result`` /
  ``token`` / ``citations`` / ``done`` / ``error``).

Tool-call / tool-result events render as collapsible inline cards. The event
vocabulary is shared between both modes, so the rendering path is identical.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Collapsible, Input, LoadingIndicator, Markdown, Static


class LiveChat(Container):
    """Input + scrollable message log wired to the orchestrator or /chat SSE."""

    DEFAULT_CSS = """
    LiveChat {
        height: 1fr;
        border: round $primary;
        border-title-color: $primary;
    }
    LiveChat #chat-log {
        height: 1fr;
        padding: 0 1;
    }
    LiveChat #chat-input {
        dock: bottom;
        border: tall $primary;
    }
    LiveChat #chat-loader {
        height: 1;
        display: none;
        color: $primary;
    }
    LiveChat #chat-loader.-busy { display: block; }
    LiveChat .human-message {
        width: 1fr; height: auto;
        border: round $primary 60%;
        border-title-color: $primary;
        padding: 0 1;
        margin: 1 1 0 1;
        color: $secondary;
    }
    LiveChat .assistant-message {
        width: 1fr; height: auto;
        border: round $accent 60%;
        border-title-color: $accent;
        padding: 0 1;
        margin: 0 1;
        transition: background 200ms, border 200ms;
    }
    LiveChat .assistant-message.-streaming { background: $accent 8%; }
    LiveChat .assistant-message:focus-within { border: round $accent; }
    LiveChat .tool-card {
        border: round $accent;
        margin: 0 2;
        color: $accent;
    }
    LiveChat .meta {
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        mode: str = "lite",
        base_url: str = "http://localhost:8000",
        locale: str = "en",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mode = mode
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.session_id = f"studio-{uuid.uuid4().hex[:8]}"
        self._answer_md: Markdown | None = None
        self._answer_buf = ""

    def compose(self) -> ComposeResult:
        self.border_title = f"live chat · {self.mode}"
        yield VerticalScroll(
            Static(
                "[dim]Ask klerk a question. "
                f"Mode: [b]{self.mode}[/b] · session {self.session_id}[/dim]",
                classes="meta",
            ),
            id="chat-log",
        )
        yield LoadingIndicator(id="chat-loader")
        yield Input(placeholder="Ask klerk…  (Enter to send)", id="chat-input")

    def _set_busy(self, busy: bool) -> None:
        """Toggle the one-row thinking spinner above the input."""
        self.query_one("#chat-loader").set_class(busy, "-busy")

    @property
    def _log(self) -> VerticalScroll:
        return self.query_one("#chat-log", VerticalScroll)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        inp = self.query_one("#chat-input", Input)
        inp.value = ""
        human = Static(query, classes="human-message")
        human.border_title = "you"
        await self._mount(human)
        self._answer_buf = ""
        self._answer_md = Markdown("", classes="assistant-message -streaming")
        self._answer_md.border_title = "klerk"
        await self._mount(self._answer_md)
        self._set_busy(True)
        if self.mode == "full":
            self._run_full(query)
        else:
            self._run_lite(query)

    async def _mount(self, widget: Any) -> None:
        await self._log.mount(widget)
        self._log.scroll_end(animate=False)

    # ── event rendering (shared by both modes) ───────────────────────────────
    async def _handle_event(self, event: str, data: dict[str, Any]) -> None:
        if event == "tool_call":
            name = data.get("display_name") or data.get("name", "tool")
            args = data.get("args", {})
            card = Collapsible(
                Static(f"args: {json.dumps(args, ensure_ascii=False)}"),
                title=f"⚙ {name}",
                collapsed=True,
                classes="tool-card",
            )
            await self._mount(card)
        elif event == "tool_result":
            name = data.get("name", "tool")
            summary = data.get("summary", "")
            await self._mount(
                Collapsible(
                    Static(summary or "[dim](no output)[/dim]"),
                    title=f"✓ {name}",
                    collapsed=True,
                    classes="tool-card",
                )
            )
        elif event == "token":
            self._answer_buf += data.get("text", "")
            if self._answer_md is not None:
                self._answer_md.update(self._answer_buf)
                self._log.scroll_end(animate=False)
        elif event == "citations":
            cites = data.get("citations", [])
            conf = data.get("confidence", 0.0)
            tail = f"_citations: {', '.join(cites) or 'none'} · confidence {conf:.2f}_"
            await self._mount(Static(tail, classes="meta"))
        elif event == "done":
            self._set_busy(False)
            if self._answer_md is not None:
                self._answer_md.remove_class("-streaming")
            await self._mount(
                Static(
                    f"[dim]done · {data.get('tool_hops', 0)} hop(s) · "
                    f"{data.get('total_ms', 0):.0f}ms[/dim]",
                    classes="meta",
                )
            )
        elif event == "error":
            self._set_busy(False)
            if self._answer_md is not None:
                self._answer_md.remove_class("-streaming")
            await self._mount(
                Static(f"[b red]error:[/b red] {data.get('detail', '?')}", classes="meta")
            )

    @staticmethod
    def _parse(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        try:
            return json.loads(payload)
        except (TypeError, ValueError):
            return {}

    # ── LITE: in-process orchestrator ─────────────────────────────────────────
    @work(exclusive=True)
    async def _run_lite(self, query: str) -> None:
        try:
            from klerk.agent.orchestrator import arun
        except Exception as e:  # noqa: BLE001
            await self._mount(
                Static(f"[b red]orchestrator unavailable:[/b red] {e}", classes="meta")
            )
            return
        try:
            async for frame in arun(query, session_id=self.session_id, locale=self.locale):
                await self._handle_event(frame["event"], self._parse(frame.get("data")))
        except Exception as e:  # noqa: BLE001
            await self._handle_event("error", {"detail": f"{type(e).__name__}: {e}"})

    # ── FULL: SSE to /chat ────────────────────────────────────────────────────
    @work(exclusive=True)
    async def _run_full(self, query: str) -> None:
        try:
            import httpx
        except Exception as e:  # noqa: BLE001
            await self._handle_event("error", {"detail": f"httpx missing: {e}"})
            return
        body = {"query": query, "locale": self.locale, "session_id": self.session_id}
        try:
            async with (
                httpx.AsyncClient(timeout=120) as client,
                client.stream("POST", f"{self.base_url}/chat", json=body) as resp,
            ):
                event = "message"
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        payload = line.split(":", 1)[1].strip()
                        await self._handle_event(event, self._parse(payload))
                    elif not line.strip():
                        event = "message"
        except Exception as e:  # noqa: BLE001
            await self._handle_event("error", {"detail": f"{type(e).__name__}: {e}"})
