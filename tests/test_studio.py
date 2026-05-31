"""Headless tests for the klerk studio dashboard (v7 Phase A.3 floor).

Every test mounts the real widgets via Textual's ``App.run_test()`` pilot so
no live LLM / HTTP is needed. The orchestrator is monkeypatched with a fake
async generator that emits klerk's SSE event vocabulary, so the lite chat
path exercises real rendering without a model.
"""

from __future__ import annotations

import json

import pytest
from textual.widgets import Collapsible, Input, Markdown

from klerk.studio.app import KlerkStudio
from klerk.studio.splash import SplashScreen
from klerk.studio.theme import KLERK_THEME
from klerk.studio.widgets import (
    ActivityTable,
    FilesTree,
    LiveChat,
    StatusBar,
    TracesPanel,
)

WIDE = (160, 48)
NARROW = (80, 24)


def test_theme_palette() -> None:
    assert KLERK_THEME.name == "klerk-cyberpunk"
    assert KLERK_THEME.dark is True
    # magenta primary + cyan secondary
    assert KLERK_THEME.primary.lower().startswith("#ff")
    assert KLERK_THEME.secondary is not None


@pytest.mark.asyncio
async def test_floor_composes_wide() -> None:
    """Wide terminal → full 5-pane floor layout mounts cleanly."""
    app = KlerkStudio(mode="lite", show_splash=False)
    async with app.run_test(size=WIDE):
        for widget in (FilesTree, LiveChat, ActivityTable, StatusBar, TracesPanel):
            assert app.query(widget), f"{widget.__name__} missing from floor"
        assert app.theme == KLERK_THEME.name


@pytest.mark.asyncio
async def test_splash_mounts_and_dismisses() -> None:
    app = KlerkStudio(mode="lite", show_splash=True)
    async with app.run_test(size=WIDE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)
        await pilot.press("space")
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)


@pytest.mark.asyncio
async def test_lite_layout_is_chat_only() -> None:
    """Narrow / --lite layout drops the side panes for a chat-only view."""
    app = KlerkStudio(mode="lite", lite_layout=True, show_splash=False)
    async with app.run_test(size=NARROW):
        assert app.query(LiveChat)
        assert not app.query(FilesTree)
        assert not app.query(ActivityTable)


@pytest.mark.asyncio
async def test_files_tree_handles_missing_roots(tmp_path, monkeypatch) -> None:
    """A fresh checkout (no corpus/state dirs) still composes."""
    monkeypatch.setenv("KLERK_CORPUS_DIR", str(tmp_path / "nope"))
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path / "state"))
    app = KlerkStudio(mode="lite", show_splash=False)
    async with app.run_test(size=WIDE):
        assert app.query(FilesTree)


@pytest.mark.asyncio
async def test_activity_table_tails_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path))
    log = tmp_path / "activity-log.jsonl"
    log.write_text(
        json.dumps(
            {
                "ts": 1_700_000_000.0,
                "tool": "search_hybrid",
                "display_name": "klerk search hybrid",
                "status": "ok",
                "duration_ms": 42.0,
                "summary": "3 hits",
            }
        )
        + "\n"
    )
    app = KlerkStudio(mode="lite", show_splash=False)
    async with app.run_test(size=WIDE) as pilot:
        await pilot.pause()
        table = app.query_one(ActivityTable)
        table.reload()
        await pilot.pause()
        dt = table.query_one("#activity-table")
        assert dt.row_count == 1


@pytest.mark.asyncio
async def test_status_bar_lite_reports_model(monkeypatch) -> None:
    app = KlerkStudio(mode="lite", show_splash=False)
    async with app.run_test(size=WIDE) as pilot:
        await pilot.pause()
        bar = app.query_one(StatusBar)
        bar.set_ctx_tokens(123)
        await pilot.pause()
        from textual.widgets import Static

        model = bar.query_one("#status-model", Static)
        clock = bar.query_one("#status-clock", Static)
        ctx = bar.query_one("#status-ctx", Static)
        # WIB clock rendered + ctx updated; never raises in lite mode.
        assert "WIB" in str(clock.render())
        assert "model:" in str(model.render())
        assert "123" in str(ctx.render())


@pytest.mark.asyncio
async def test_lite_chat_renders_tool_cards_and_tokens(monkeypatch) -> None:
    """Mocked orchestrator stream → tool cards + streamed answer render."""

    async def fake_arun(query, *, session_id, locale="en", history=None):  # noqa: ANN001
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}
        yield {
            "event": "tool_call",
            "data": json.dumps(
                {"name": "search_hybrid", "display_name": "klerk search hybrid", "args": {"q": query}}
            ),
        }
        yield {
            "event": "tool_result",
            "data": json.dumps({"name": "search_hybrid", "summary": "3 hits"}),
        }
        yield {"event": "token", "data": json.dumps({"text": "Hello "})}
        yield {"event": "token", "data": json.dumps({"text": "world."})}
        yield {
            "event": "citations",
            "data": json.dumps({"citations": ["doc:1"], "confidence": 0.7}),
        }
        yield {"event": "done", "data": json.dumps({"tool_hops": 1, "total_ms": 12.3})}

    import klerk.agent.orchestrator as orch

    monkeypatch.setattr(orch, "arun", fake_arun)

    app = KlerkStudio(mode="lite", show_splash=False)
    async with app.run_test(size=WIDE) as pilot:
        await pilot.pause()
        chat = app.query_one(LiveChat)
        inp = chat.query_one("#chat-input", Input)
        await chat.on_input_submitted(Input.Submitted(inp, "what is the leave policy?"))
        # let the @work coroutine drain
        for _ in range(4):
            await pilot.pause(0.1)
        cards = chat.query(Collapsible)
        mds = chat.query(Markdown)
        assert len(cards) >= 2  # tool_call + tool_result
        assert any("world" in (m._markdown or "") for m in mds)


@pytest.mark.asyncio
async def test_full_mode_chat_parses_sse(monkeypatch) -> None:
    """Full mode parses an SSE byte stream from a mocked httpx client."""
    import httpx

    sse = (
        "event: tool_call\n"
        'data: {"name": "search_hybrid", "display_name": "klerk search hybrid", "args": {}}\n\n'
        "event: token\n"
        'data: {"text": "Hi there."}\n\n'
        "event: done\n"
        'data: {"tool_hops": 1, "total_ms": 5.0}\n\n'
    )

    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def aiter_lines(self):
            for line in sse.split("\n"):
                yield line

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            return FakeStream()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    app = KlerkStudio(mode="full", show_splash=False)
    async with app.run_test(size=WIDE) as pilot:
        await pilot.pause()
        chat = app.query_one(LiveChat)
        inp = chat.query_one("#chat-input", Input)
        await chat.on_input_submitted(Input.Submitted(inp, "hi"))
        for _ in range(4):
            await pilot.pause(0.1)
        mds = chat.query(Markdown)
        assert any("Hi there" in (m._markdown or "") for m in mds)


@pytest.mark.asyncio
async def test_traces_panel_composes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path))
    app = KlerkStudio(mode="lite", show_splash=False)
    async with app.run_test(size=WIDE):
        assert app.query(TracesPanel)


@pytest.mark.asyncio
async def test_bonus_panes_mount_and_degrade(tmp_path, monkeypatch) -> None:
    """Bonus panes mount in the right rail and render hints with no data."""
    from klerk.studio.widgets.eval_panel import EvalPanel
    from klerk.studio.widgets.graph import SparkGraph
    from klerk.studio.widgets.kg_snapshot import KgSnapshot

    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("KLERK_KG_DIR", str(tmp_path / "kg"))
    app = KlerkStudio(mode="lite", show_splash=False, show_bonus=True)
    async with app.run_test(size=(160, 60)):
        assert app.query(EvalPanel)
        assert app.query(KgSnapshot)
        assert app.query(SparkGraph)


@pytest.mark.asyncio
async def test_eval_panel_reads_rubric(tmp_path, monkeypatch) -> None:
    runs = tmp_path / "eval-runs"
    runs.mkdir()
    (runs / "latest.json").write_text(
        json.dumps(
            {
                "aggregate": {"overall": {"mean": 0.81, "confidence": 0.7}},
                "ragas": {"aggregate": {"faithfulness": 0.9}},
            }
        )
    )
    monkeypatch.setenv("KLERK_STATE_DIR", str(tmp_path))
    from textual.widgets import DataTable

    from klerk.studio.widgets.eval_panel import EvalPanel

    app = KlerkStudio(mode="lite", show_splash=False, show_bonus=True)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        panel = app.query_one(EvalPanel)
        dt = panel.query_one(DataTable)
        assert dt.row_count >= 1


def test_bonus_builder_swallows_import_errors(monkeypatch) -> None:
    """A broken bonus import must not break the floor."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if "kg_snapshot" in name:
            raise ImportError("boom")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from klerk.studio import app as studio_app

    widgets = studio_app._bonus_widgets()
    # eval + sparklines still present; kg dropped, no exception raised.
    names = {type(w).__name__ for w in widgets}
    assert "KgSnapshot" not in names


def test_serve_guarded_without_textual_serve(monkeypatch) -> None:
    """serve() raises an actionable error when textual-serve is absent."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("textual_serve"):
            raise ModuleNotFoundError("No module named 'textual_serve'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from klerk.studio import app as studio_app

    with pytest.raises(RuntimeError, match="textual-serve"):
        studio_app.serve()
