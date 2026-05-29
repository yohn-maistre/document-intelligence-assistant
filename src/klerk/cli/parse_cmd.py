"""`klerk parse <path>` — exercise the unified parser, dump preview to stdout."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from klerk.parse import parse

console = Console()


def parse_cmd(
    path: Annotated[Path, typer.Argument(help="File to parse.", exists=True, resolve_path=True)],
    preview: Annotated[int, typer.Option("--preview", "-n", help="Chars to preview.")] = 400,
) -> None:
    """Parse one file and print metadata + a text preview."""
    doc = parse(path)

    table = Table(title=f"Parsed: {doc.source.name}", show_header=False, border_style="dim")
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("doc_id", doc.doc_id)
    table.add_row("locale", doc.locale)
    table.add_row("parser", str(doc.meta.get("parser", "?")))
    table.add_row("suffix", str(doc.meta.get("suffix", "?")))
    table.add_row("text length", f"{len(doc.text):,} chars")
    if "page_count" in doc.meta and doc.meta["page_count"]:
        table.add_row("pages", str(doc.meta["page_count"]))
    console.print(table)

    preview_text = doc.text[:preview]
    if len(doc.text) > preview:
        preview_text += "\n\n[dim]... (truncated)[/dim]"
    console.print(Panel(preview_text, title="preview", border_style="cyan"))
