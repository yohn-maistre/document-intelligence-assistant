"""`klerk faq build` — Corpus Learning Agent → auto-FAQ."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from klerk.agent import faq as faq_mod

console = Console()


def build_cmd(
    per_doc: Annotated[int, typer.Option("--per-doc", help="Max questions per doc.")] = 5,
) -> None:
    """Generate questions per doc, answer via CRAG, emit data/output/faq.md."""
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as prog:
        prog.add_task("Building FAQ (proposing + answering)...", total=None)
        try:
            entries = faq_mod.build(per_doc_q_cap=per_doc)
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

    if not entries:
        console.print(Panel("No FAQ entries generated.", border_style="yellow"))
        raise typer.Exit(code=0)

    by_doc: dict[str, int] = {}
    for e in entries:
        by_doc[e.doc_id] = by_doc.get(e.doc_id, 0) + 1
    table = Table(title=f"FAQ generated — {len(entries)} entries", border_style="green")
    table.add_column("doc_id")
    table.add_column("Q&A pairs", justify="right")
    for doc_id, n in sorted(by_doc.items()):
        table.add_row(doc_id, str(n))
    console.print(table)

    path = faq_mod.save(entries)
    console.print(f"\n[green]✓[/green] FAQ written: [cyan]{path}[/cyan]")
