"""`klerk extract-actions` — Brief Option B (Action Item Extractor).

Thin CLI wrapper over :func:`klerk.agent.action_items.extract` (PydanticAI typed
one-shot). Pass either a ``--doc-id`` (chunks pulled from LanceDB, with
chunk-level grounding) or ``--text`` (a pasted snippet, e.g. meeting minutes).
Human surface is a Rich table; ``--agent`` emits the structured
``ActionExtraction`` as JSON.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from klerk.agent.action_items import extract
from klerk.cli._agent_flag import agent_console, emit, with_agent_mode

console = agent_console()


@with_agent_mode
def extract_actions_cmd(
    text: Annotated[
        str | None,
        typer.Option("--text", "-t", help="Free-text snippet (e.g. pasted meeting minutes)."),
    ] = None,
    doc_id: Annotated[
        str | None,
        typer.Option("--doc-id", "-d", help="Extract from an indexed doc by id (chunk-grounded)."),
    ] = None,
    locale: Annotated[str, typer.Option("--locale", "-l", help="en | id")] = "en",
) -> None:
    """Pull structured action items (assignee · action · due · priority)."""
    if doc_id is None and text is None:
        console.print("[red]Pass either --doc-id or --text.[/red]")
        raise typer.Exit(code=1)

    try:
        result = extract(doc_id=doc_id, text=text, locale=locale)
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    table = Table(title=f"Action items · source={result.source}", border_style="green")
    table.add_column("#", justify="right", style="dim")
    table.add_column("assignee", style="cyan")
    table.add_column("action")
    table.add_column("due", style="dim")
    table.add_column("priority", justify="center")
    table.add_column("source_chunk", style="dim")
    for i, item in enumerate(result.items, 1):
        table.add_row(
            str(i),
            item.assignee,
            item.action,
            item.due or "—",
            item.priority,
            item.source_chunk or "—",
        )
    if result.items:
        console.print(table)
    else:
        console.print("[yellow]No action items found.[/yellow]")

    emit(result.model_dump())
