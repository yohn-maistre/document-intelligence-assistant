"""`klerk index` — build, stats."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from klerk.parse import parse
from klerk.rag.chunker import chunk_text
from klerk.rag.store import reset_corpus, stats, upsert_chunks

console = Console()


def build(
    src: Annotated[Path, typer.Option("--src", "-s", help="Source directory of docs.")] = Path("data/seed"),
    rebuild: Annotated[bool, typer.Option("--rebuild", help="Drop existing corpus table first.")] = False,
    max_tokens: Annotated[int, typer.Option("--max-tokens", help="Chunker target size.")] = 384,
    overlap: Annotated[int, typer.Option("--overlap", help="Inter-chunk token overlap.")] = 64,
) -> None:
    """Parse every doc under `--src`, chunk, embed, and upsert to LanceDB."""
    if not src.exists():
        console.print(f"[red]index build: source dir not found: {src}[/red]")
        raise typer.Exit(code=1)

    if rebuild:
        console.print("[dim]rebuild=True → dropping corpus table...[/dim]")
        reset_corpus()

    files = [p for p in sorted(src.rglob("*")) if p.is_file() and p.name != "README.md"]
    if not files:
        console.print(f"[yellow]No files found under {src}[/yellow]")
        raise typer.Exit(code=0)

    total_chunks = 0
    by_doc: dict[str, int] = {}

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True
    ) as prog:
        task = prog.add_task(f"Indexing {len(files)} file(s)...", total=None)
        for f in files:
            try:
                doc = parse(f)
            except Exception as e:  # noqa: BLE001
                console.print(f"  [yellow]skip {f.name}: {type(e).__name__}: {e}[/yellow]")
                continue

            chunks = chunk_text(
                doc.text,
                doc_id=doc.doc_id,
                locale=doc.locale,
                source=str(doc.source),
                max_tokens=max_tokens,
                overlap_tokens=overlap,
            )
            if not chunks:
                console.print(f"  [yellow]skip {f.name}: no chunks emitted[/yellow]")
                continue

            n = upsert_chunks(chunks)
            total_chunks += n
            by_doc[doc.doc_id] = n
            prog.update(task, description=f"Indexed {doc.doc_id}: {n} chunk(s)")

    # Report
    table = Table(title=f"Index built ({src})", border_style="green")
    table.add_column("doc_id")
    table.add_column("chunks", justify="right")
    for doc_id, n in by_doc.items():
        table.add_row(doc_id, str(n))
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total_chunks}[/bold]")
    console.print(table)


def show_stats() -> None:
    """Print current corpus stats."""
    s = stats()
    if s is None:
        console.print("[yellow]No corpus table yet — run `klerk index build` first.[/yellow]")
        raise typer.Exit(code=0)
    table = Table(title="Index stats", show_header=False, border_style="dim")
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("table", s.table)
    table.add_row("rows", str(s.n_rows))
    table.add_row("embed dim", str(s.embed_dim))
    table.add_row("FTS indexed", "yes" if s.fts_indexed else "no")
    console.print(table)
