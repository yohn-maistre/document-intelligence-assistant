"""CLI verbs for SHOULD-tier features: anomaly · kg viz · bg · trace."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from klerk.agent import anomaly as anomaly_mod
from klerk.agent import background as bg_mod
from klerk.agent import kg_extract, kg_viz, checkpoint as checkpoint_mod

console = Console()


# ─── anomaly scan ────────────────────────────────────────────────────────────
def anomaly_scan_cmd(
    sigma: Annotated[float, typer.Option("--sigma", help="z-score threshold.")] = 2.0,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en",
) -> None:
    """Surface outlier docs that don't fit the corpus pattern."""
    try:
        hits = anomaly_mod.scan(sigma=sigma, locale=locale)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    if not hits:
        console.print(Panel("No outliers detected.", border_style="green"))
    else:
        table = Table(title=f"{len(hits)} outlier(s) at σ ≥ {sigma}", border_style="yellow")
        table.add_column("doc_id", style="yellow")
        table.add_column("z-score", justify="right")
        table.add_column("chunks", justify="right")
        table.add_column("justification")
        for h in hits:
            table.add_row(h.doc_id, f"{h.z_score:.2f}", str(h.n_chunks), h.justification[:140] + ("…" if len(h.justification) > 140 else ""))
        console.print(table)

    path = anomaly_mod.save_report(hits)
    console.print(f"\n[green]✓[/green] Report: [cyan]{path}[/cyan]")


# ─── kg viz ──────────────────────────────────────────────────────────────────
def kg_viz_cmd(
    out: Annotated[Path, typer.Option("--out", help="Output HTML path.")] = Path("data/output/kg.html"),
) -> None:
    """Render the KG to interactive HTML (pyvis) or a static fallback."""
    g = kg_extract.load_graph()
    if g.number_of_nodes() == 0:
        console.print("[yellow]Graph empty — run `klerk kg extract` first.[/yellow]")
        raise typer.Exit(code=0)
    path = kg_viz.render_html(g, out)
    console.print(Panel(f"Rendered {g.number_of_nodes()} entities / {g.number_of_edges()} relations\n→ [cyan]{path}[/cyan]", border_style="green"))


# ─── bg start | status ───────────────────────────────────────────────────────
def bg_start_cmd(
    interval: Annotated[int, typer.Option("--interval", help="Seconds between cycles.")] = 60,
    once: Annotated[bool, typer.Option("--once", help="Run one cycle then exit.")] = False,
) -> None:
    """Run the background ingestion agent (APScheduler)."""
    if once:
        report = bg_mod.run_cycle()
        _render_cycle(report)
        return

    console.print(Panel(f"Background ingestion: watching every {interval}s.\nCtrl-C to stop.", border_style="cyan"))
    try:
        bg_mod.start(interval_seconds=interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]stopped.[/yellow]")


def bg_status_cmd() -> None:
    """Show the last completed cycle's report."""
    report = bg_mod.last_report()
    if report is None:
        console.print("[yellow]No cycle has run yet. Try `klerk bg start --once`.[/yellow]")
        raise typer.Exit(code=0)
    _render_cycle(report)


def _render_cycle(report: bg_mod.CycleReport) -> None:
    table = Table(title=f"Cycle @ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report.cycle_ts))}", border_style="green", show_header=False)
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("watched", report.watched_dir)
    table.add_row("added", str(report.n_added))
    table.add_row("changed", str(report.n_changed))
    table.add_row("removed", str(report.n_removed))
    table.add_row("indexed (chunks)", str(report.n_indexed))
    if report.errors:
        table.add_row("[red]errors[/red]", "\n".join(report.errors))
    console.print(table)


# ─── trace list / show (checkpoint introspection) ────────────────────────────
def trace_list_cmd(
    op: Annotated[str | None, typer.Option("--op", help="Filter to one op: propose | faq | ...")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
) -> None:
    """List recent checkpoint runs (for mid-run resumability)."""
    runs = checkpoint_mod.list_runs(op=op, limit=limit)
    if not runs:
        console.print("[yellow]No runs recorded yet.[/yellow]")
        raise typer.Exit(code=0)
    table = Table(title=f"{len(runs)} run(s){f' (op={op})' if op else ''}", border_style="cyan")
    table.add_column("run_id", style="cyan")
    table.add_column("op")
    table.add_column("topic", overflow="fold")
    table.add_column("locale", style="dim")
    table.add_column("status", justify="center")
    table.add_column("started")
    for r in runs:
        status = "[green]✓[/green]" if r["completed_at"] else "[yellow]…[/yellow]"
        started = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["started_at"])) if r["started_at"] else "—"
        table.add_row(r["run_id"], r["op"], r["topic"] or "—", r["locale"] or "—", status, started)
    console.print(table)
