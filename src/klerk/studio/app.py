"""Textual Studio TUI — `klerk studio` (and `textual serve` for browser).

Refactored layout (v5, step 9 of the implementation plan):

  1. Chat       — primary view; recent /chat traces + entry-point hints
                  for interactive use via klerk-api / `klerk ask`.
  2. Corpus     — LanceDB corpus table read-out.
  3. Eval       — data/output/eval/*.json (rubric + RAGAS).
  4. Traces     — Phoenix span snapshot, LangGraph checkpoints, drift events.
  5. Outputs    — five sub-tabs over data/output/* artefacts:
                    Escalations  /  Action Items  /  Conflicts  /
                    Drafts       /  Drift

The Studio remains predominantly read-only over klerk's artefacts — the
verbs and the FastAPI surface own execution. The Chat panel surfaces
recent activity from .klerk/chat-history.jsonl (written by the FastAPI
audit hook when KLERK_CHAT_HISTORY=1) and explains how to drive a fresh
conversation through the API.

Drop relative to v4: KG panel (klerk's KG is internal-only; no value in
visualising it for the brief). Proposals tab is now Outputs with 5
sub-tabs since step 7 ships 5 distinct artefact streams.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Markdown,
    Static,
    TabbedContent,
    TabPane,
)


# ─── Data loaders (best-effort, never throw) ─────────────────────────────────
def _state_dir() -> Path:
    return Path(os.environ.get("KLERK_STATE_DIR", ".klerk"))


def _corpus_rows() -> list[dict[str, Any]]:
    try:
        from klerk.rag.store import CORPUS_TABLE, open_db
    except Exception:  # noqa: BLE001
        return []
    try:
        db = open_db()
        if CORPUS_TABLE not in db.list_tables():
            return []
        df = db.open_table(CORPUS_TABLE).to_pandas()
    except Exception:  # noqa: BLE001
        return []
    rows = df.to_dict("records")
    for r in rows:
        r.pop("vector", None)
    return rows


def _eval_blob() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ("rubric", "ragas"):
        p = Path(f"data/output/eval/{name}.json")
        if p.exists():
            try:
                out[name] = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                out[name] = {"error": "could not parse JSON"}
    return out


def _drift_events(limit: int = 50) -> list[dict[str, Any]]:
    p = _state_dir() / "drift-events.jsonl"
    if not p.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in p.read_text().splitlines()[-limit:]:
            if line.strip():
                events.append(json.loads(line))
    except Exception:  # noqa: BLE001
        return []
    return events


def _ingest_runs(limit: int = 20) -> list[dict[str, Any]]:
    d = _state_dir() / "ingest-runs"
    if not d.exists():
        return []
    runs: list[dict[str, Any]] = []
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[:limit]:
        try:
            runs.append(json.loads(f.read_text()))
        except Exception:  # noqa: BLE001
            continue
    return runs


def _chat_history(limit: int = 20) -> list[dict[str, Any]]:
    """Recent /chat traces, written by the FastAPI audit hook (opt-in)."""
    p = _state_dir() / "chat-history.jsonl"
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in p.read_text().splitlines()[-limit:]:
            if line.strip():
                out.append(json.loads(line))
    except Exception:  # noqa: BLE001
        return []
    return out


def _artefact_files(category: str) -> list[Path]:
    """Files under data/output/{category}/, sorted newest first."""
    d = Path(f"data/output/{category}")
    if not d.exists():
        return []
    return sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)


# ─── Panels ──────────────────────────────────────────────────────────────────
class ChatPanel(Container):
    def compose(self) -> ComposeResult:
        history = _chat_history()
        if not history:
            yield ScrollableContainer(
                Markdown(
                    "# Chat\n\n"
                    "The Studio's Chat panel surfaces recent conversations from "
                    "`.klerk/chat-history.jsonl`. To drive a live conversation:\n\n"
                    "## API (primary)\n\n"
                    "```\n"
                    "curl -N -X POST http://localhost:8000/chat \\\n"
                    "  -H 'Content-Type: application/json' \\\n"
                    "  -d '{\"query\": \"What is the parental leave policy?\", \"locale\": \"en\"}'\n"
                    "```\n\n"
                    "## CLI\n\n"
                    "```\n"
                    "klerk ask \"What is the parental leave policy?\"\n"
                    "```\n\n"
                    "## Enable chat-history logging\n\n"
                    "Set `KLERK_CHAT_HISTORY=1` and the API will append each "
                    "exchange to `.klerk/chat-history.jsonl` for inspection here."
                )
            )
            return
        yield Static(f"[bold]{len(history)} recent exchange(s)[/bold]")
        for h in history[-10:]:
            yield Markdown(
                f"### Q: {h.get('query', '')}\n\n"
                f"_locale={h.get('locale', '?')}  "
                f"confidence={h.get('confidence', '?')}  "
                f"ttft_ms={h.get('ttft_ms', '?')}_\n\n"
                f"{h.get('answer', '(no answer)')}"
            )


class CorpusPanel(Container):
    def compose(self) -> ComposeResult:
        rows = _corpus_rows()
        if not rows:
            yield Static(
                "[dim]No corpus indexed. Run "
                "[cyan]klerk index build --src data/synth/fata_organa --rebuild[/cyan] "
                "first.[/dim]"
            )
            return
        by_doc: dict[str, int] = {}
        for r in rows:
            by_doc[r["doc_id"]] = by_doc.get(r["doc_id"], 0) + 1
        yield Static(f"[bold]{len(rows)} chunks across {len(by_doc)} docs[/bold]")
        table = DataTable(id="corpus-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("chunk_id", "doc_id", "locale", "n_tokens", "preview")
        for r in rows:
            preview = r["text"].replace("\n", " ").strip()
            if len(preview) > 90:
                preview = preview[:90] + "…"
            table.add_row(
                r["chunk_id"],
                r["doc_id"],
                r.get("locale", "?"),
                str(r.get("n_tokens", "?")),
                preview,
            )
        yield table


class EvalPanel(Container):
    def compose(self) -> ComposeResult:
        blob = _eval_blob()
        if not blob:
            yield Static(
                "[dim]No eval output yet. Run [cyan]klerk eval run[/cyan].[/dim]"
            )
            return
        body_lines: list[str] = []
        if "rubric" in blob and "aggregate" in blob["rubric"]:
            overall = blob["rubric"]["aggregate"].get("overall", {})
            body_lines.append("## klerk 5-axis rubric (overall)")
            for axis in (
                "retrieval_recall",
                "substring_coverage",
                "citation_grounded",
                "locale_match",
                "confidence",
                "mean",
            ):
                if axis in overall:
                    body_lines.append(f"- **{axis}**: {overall[axis]:.2f}")
            body_lines.append("")
            by_loc = blob["rubric"]["aggregate"].get("by_locale", {})
            if by_loc:
                body_lines.append("### by locale")
                for loc, s in by_loc.items():
                    body_lines.append(
                        f"- **{loc}**: mean={s.get('mean', 0):.2f}  n={s.get('n', 0)}"
                    )
                body_lines.append("")
        if "ragas" in blob and blob["ragas"].get("aggregate"):
            body_lines.append("## RAGAS baseline")
            for k, v in blob["ragas"]["aggregate"].items():
                body_lines.append(f"- **{k}**: {v:.2f}")
        yield ScrollableContainer(Markdown("\n".join(body_lines)))


class TracesPanel(Container):
    """Drift events + ingest runs + LangGraph checkpoint summary."""

    def compose(self) -> ComposeResult:
        drift = _drift_events()
        runs = _ingest_runs()
        lg_db = _state_dir() / "langgraph-state.db"

        body: list[str] = []
        body.append(f"## Drift events ({len(drift)})")
        if not drift:
            body.append("- _none yet — run `POST /drift/scan` or `klerk drive sync`_")
        else:
            for ev in drift[-10:]:
                body.append(
                    f"- **{ev.get('type', '?')}** {ev.get('doc_id', '?')} "
                    f"`{ev.get('timestamp', '?')}` — {ev.get('summary', '')}"
                )
        body.append("")
        body.append(f"## Ingest runs ({len(runs)})")
        if not runs:
            body.append("- _none yet — POST /ingest to trigger one_")
        else:
            for r in runs[:10]:
                body.append(
                    f"- `{r.get('run_id', '?')}` source={r.get('source', '?')} "
                    f"state={r.get('state', '?')} "
                    f"n_chunks={r.get('n_chunks', 0)}"
                )
        body.append("")
        body.append("## LangGraph checkpoints")
        body.append(
            f"- file: `{lg_db}` "
            f"{'(present)' if lg_db.exists() else '(not seeded — no scans yet)'}"
        )
        yield ScrollableContainer(Markdown("\n".join(body)))


class OutputsPanel(Container):
    """Five sub-tabs over data/output/* artefacts."""

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="conflicts"):
            with TabPane("Escalations", id="escalations"):
                yield self._files_view("escalations")
            with TabPane("Action Items", id="actions"):
                yield self._files_view("actions")
            with TabPane("Conflicts", id="conflicts"):
                yield self._latest_file("contradictions.md", "data/output")
            with TabPane("Drafts", id="drafts"):
                yield self._files_view("proposals")
            with TabPane("Drift", id="drift"):
                yield self._drift_summary()

    def _files_view(self, category: str) -> Container:
        files = _artefact_files(category)
        if not files:
            return Static(
                f"[dim]No {category} artefacts yet. They land under "
                f"data/output/{category}/ when the corresponding "
                f"capability runs.[/dim]"
            )
        latest = files[0]
        try:
            body = latest.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            body = f"_(unreadable: {e})_"
        return ScrollableContainer(
            Static(
                f"[bold]{len(files)} file(s) · latest: {latest.name}[/bold]\n"
            ),
            Markdown(body),
        )

    def _latest_file(self, fname: str, dir_: str) -> Container:
        p = Path(dir_) / fname
        if not p.exists():
            return Static(
                f"[dim]{fname} not generated yet. Run "
                f"`POST /conflicts/scan` or `klerk contradict scan`.[/dim]"
            )
        try:
            body = p.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            body = f"_(unreadable: {e})_"
        return ScrollableContainer(Markdown(body))

    def _drift_summary(self) -> Container:
        events = _drift_events()
        if not events:
            return Static(
                "[dim]No drift events yet. Run "
                "`POST /drift/scan` or wait for the scheduled nightly run.[/dim]"
            )
        lines = ["# Recent drift events", ""]
        for ev in events[-20:]:
            lines.append(
                f"- **{ev.get('type', '?')}** {ev.get('doc_id', '?')}"
            )
            lines.append(f"  - {ev.get('summary', '')}")
            lines.append(f"  - _ts: {ev.get('timestamp', '?')}_")
        return ScrollableContainer(Markdown("\n".join(lines)))


# ─── App shell ───────────────────────────────────────────────────────────────
class KlerkStudio(App):
    CSS = """
    Screen {
        background: #0f1115;
        color: #e6e6e6;
    }
    TabbedContent {
        background: #0f1115;
    }
    DataTable {
        background: #131722;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("r", "reload", "reload"),
        Binding("1", "show_tab('chat')", "chat"),
        Binding("2", "show_tab('corpus')", "corpus"),
        Binding("3", "show_tab('eval')", "eval"),
        Binding("4", "show_tab('traces')", "traces"),
        Binding("5", "show_tab('outputs')", "outputs"),
    ]

    TITLE = "klerk studio"
    SUB_TITLE = "operator panel — chat / corpus / eval / traces / outputs"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="chat"):
            with TabPane("Chat", id="chat"):
                yield ChatPanel()
            with TabPane("Corpus", id="corpus"):
                yield CorpusPanel()
            with TabPane("Eval", id="eval"):
                yield EvalPanel()
            with TabPane("Traces", id="traces"):
                yield TracesPanel()
            with TabPane("Outputs", id="outputs"):
                yield OutputsPanel()
        yield Footer()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_reload(self) -> None:
        self.refresh(recompose=True)


def main() -> None:
    """Entry point for [project.scripts] klerk-studio = ..."""
    serve = "--serve" in sys.argv[1:]
    if serve:
        # textual >= 0.86 ships `textual serve` as a first-class browser
        # deploy. We just shell out so the user can stop / restart easily.
        os.execvp("textual", ["textual", "serve", "klerk.studio.app:main"])
    KlerkStudio().run()


if __name__ == "__main__":
    main()
