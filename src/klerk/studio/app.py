"""Textual Studio TUI — `klerk studio`.

Five panels, each reading from an artifact klerk already produces:

  Corpus     ← LanceDB corpus table
  Eval       ← data/output/eval/*.json
  Traces     ← .klerk/checkpoints.db (+ Phoenix SQLite when present)
  Proposals  ← data/output/proposals/*.md
  KG         ← data/kg/graph.json

The TUI never *runs* klerk's pipelines — that's what the CLI verbs are for.
This is the operator's read-only inspection surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Markdown,
    Static,
    TabbedContent,
    TabPane,
)


# ─── Data loaders ────────────────────────────────────────────────────────────
def _corpus_rows() -> list[dict[str, Any]]:
    try:
        from klerk.rag.store import CORPUS_TABLE, open_db
    except Exception:  # noqa: BLE001
        return []
    try:
        db = open_db()
        if CORPUS_TABLE not in db.table_names():
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
    for name in ("rubric", "seahelm", "ragas"):
        p = Path(f"data/output/eval/{name}.json")
        if p.exists():
            try:
                out[name] = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                out[name] = {"error": "could not parse JSON"}
    return out


def _runs() -> list[dict[str, Any]]:
    try:
        from klerk.agent.checkpoint import list_runs
    except Exception:  # noqa: BLE001
        return []
    try:
        return list_runs(limit=100)
    except Exception:  # noqa: BLE001
        return []


def _proposals() -> list[Path]:
    p = Path("data/output/proposals")
    return sorted(p.glob("*.md")) if p.exists() else []


def _kg_summary() -> dict[str, Any]:
    try:
        from klerk.agent.kg_extract import load_graph

        g = load_graph()
    except Exception:  # noqa: BLE001
        return {"entities": 0, "relations": 0, "by_type": {}}
    by_type: dict[str, int] = {}
    for _, attrs in g.nodes(data=True):
        t = attrs.get("type", "other")
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "entities": g.number_of_nodes(),
        "relations": g.number_of_edges(),
        "by_type": by_type,
    }


# ─── Panels ──────────────────────────────────────────────────────────────────
class CorpusPanel(Container):
    def compose(self) -> ComposeResult:
        rows = _corpus_rows()
        if not rows:
            yield Static(
                "[dim]No corpus indexed. Run [cyan]klerk index build --src data/seed --rebuild[/cyan] first.[/dim]",
                id="corpus-empty",
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
            table.add_row(r["chunk_id"], r["doc_id"], r.get("locale", "?"), str(r.get("n_tokens", "?")), preview)
        yield table


class EvalPanel(Container):
    def compose(self) -> ComposeResult:
        blob = _eval_blob()
        if not blob:
            yield Static(
                "[dim]No eval output yet. Run [cyan]klerk eval run[/cyan] to populate.[/dim]"
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
                    body_lines.append(f"- **{loc}**: mean={s.get('mean', 0):.2f}  n={s.get('n', 0)}")
                body_lines.append("")
        if "seahelm" in blob:
            delta = blob["seahelm"].get("id_minus_en_delta", {})
            if delta:
                body_lines.append("## SEA-HELM-style Bahasa parity (Δ = id − en)")
                for axis, d in delta.items():
                    arrow = "→" if abs(d) < 0.1 else "↑" if d > 0 else "↓"
                    body_lines.append(f"- **{axis}**: {d:+.2f}  {arrow}")
                body_lines.append("")
        if "ragas" in blob and blob["ragas"].get("aggregate"):
            body_lines.append("## RAGAS baseline")
            for k, v in blob["ragas"]["aggregate"].items():
                body_lines.append(f"- **{k}**: {v:.2f}")
        yield ScrollableContainer(Markdown("\n".join(body_lines)))


class TracesPanel(Container):
    def compose(self) -> ComposeResult:
        runs = _runs()
        if not runs:
            yield Static("[dim]No runs recorded yet. Run [cyan]klerk propose ...[/cyan] or [cyan]klerk faq build[/cyan].[/dim]")
            return
        yield Static(f"[bold]{len(runs)} checkpoint run(s)[/bold]")
        table = DataTable(id="runs-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("run_id", "op", "topic", "locale", "status")
        for r in runs:
            status = "✓" if r.get("completed_at") else "in-progress"
            table.add_row(
                r["run_id"], r["op"], r.get("topic") or "—", r.get("locale") or "—", status
            )
        yield table


class ProposalsPanel(Container):
    def compose(self) -> ComposeResult:
        files = _proposals()
        if not files:
            yield Static(
                "[dim]No proposals yet. Run [cyan]klerk propose \"<topic>\"[/cyan] to generate one.[/dim]"
            )
            return
        latest = files[-1]
        body = latest.read_text(encoding="utf-8")
        yield Static(f"[bold]{len(files)} proposal(s) · showing latest: {latest.name}[/bold]")
        yield ScrollableContainer(Markdown(body))


class KgPanel(Container):
    def compose(self) -> ComposeResult:
        s = _kg_summary()
        if s["entities"] == 0:
            yield Static(
                "[dim]Graph empty. Run [cyan]klerk kg extract --rebuild[/cyan] first.[/dim]"
            )
            return
        body = [
            f"## Knowledge graph",
            "",
            f"- **entities**: {s['entities']}",
            f"- **relations**: {s['relations']}",
            "",
            "### entities by type",
        ]
        for ent_type, count in sorted(s["by_type"].items(), key=lambda kv: -kv[1]):
            body.append(f"- **{ent_type}**: {count}")
        body.append("")
        body.append(
            "*Run `klerk kg viz` to render an interactive HTML view at "
            "`data/output/kg.html`.*"
        )
        yield ScrollableContainer(Markdown("\n".join(body)))


# ─── App ─────────────────────────────────────────────────────────────────────
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
    .panel-empty {
        padding: 2 4;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("r", "reload", "reload"),
        Binding("1", "show_tab('corpus')", "corpus"),
        Binding("2", "show_tab('eval')", "eval"),
        Binding("3", "show_tab('traces')", "traces"),
        Binding("4", "show_tab('proposals')", "proposals"),
        Binding("5", "show_tab('kg')", "kg"),
    ]

    TITLE = "klerk studio"
    SUB_TITLE = "operator panel — read-only over klerk's artifacts"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="corpus"):
            with TabPane("Corpus", id="corpus"):
                yield CorpusPanel()
            with TabPane("Eval", id="eval"):
                yield EvalPanel()
            with TabPane("Traces", id="traces"):
                yield TracesPanel()
            with TabPane("Proposals", id="proposals"):
                yield ProposalsPanel()
            with TabPane("KG", id="kg"):
                yield KgPanel()
        yield Footer()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_reload(self) -> None:
        """Recreate the current screen so panels re-read their data sources."""
        self.refresh(recompose=True)


def main() -> None:
    """Entry point exposed via [project.scripts] klerk-studio = ..."""
    serve = "--serve" in sys.argv[1:]
    if serve:
        # textual-web isn't installed by default (deferred from MUST tier);
        # the path is documented for the reviewer.
        print(
            "klerk studio --serve requires textual-web in a separate venv.\n"
            "See docs/design-decisions.md for the STRETCH browser-deploy path.",
            file=sys.stderr,
        )
        sys.exit(2)
    KlerkStudio().run()


if __name__ == "__main__":
    main()
