"""CLI verbs for SHOULD-tier features: anomaly · kg viz.

`bg` (background ingestion) and `trace` (checkpoint introspection) were
demoted in the v5 cleanup pass — see `experimental/README.md`. The diff /
manifest primitive that powered `bg` was extracted to `klerk.drive.sync`
for step 3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from klerk.agent import anomaly as anomaly_mod
from klerk.agent import kg_extract, kg_viz

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
