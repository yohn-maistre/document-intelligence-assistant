"""`klerk memory {recall,save,show-soul,edit-soul}` — operate on the Hermes trio.

Plain Rich output for humans; the shared Midday ``--agent`` / ``--json`` mode
(from :mod:`klerk.cli._agent_flag`) emits exactly one JSON object on stdout for
agent consumers. ``edit-soul`` is interactive (it launches ``$EDITOR``) so it
stays human-only.
"""

from __future__ import annotations

import os
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from klerk.cli._agent_flag import agent_console, emit, with_agent_mode
from klerk.memory import MemoryStore

console = agent_console()

MAX_PREVIEW_CHARS = 200


def _store() -> MemoryStore:
    return MemoryStore()


@with_agent_mode
def recall(
    query: Annotated[str, typer.Argument(help="What to recall.")],
    k: Annotated[int, typer.Option("--k", "-k", help="Max facts to return.")] = 4,
) -> None:
    """Recall durable facts (hybrid vector + BM25, RRF-fused)."""
    facts = _store().recall(query, k=k)
    if not facts:
        console.print("[dim]No facts recalled.[/dim]")
    else:
        table = Table(title=f"Recalled {len(facts)} fact(s)", border_style="cyan")
        table.add_column("#", style="dim", justify="right")
        table.add_column("score", justify="right")
        table.add_column("kind", style="dim")
        table.add_column("fact")
        for i, f in enumerate(facts, 1):
            text = f.fact if len(f.fact) <= MAX_PREVIEW_CHARS else f.fact[:MAX_PREVIEW_CHARS] + "…"
            table.add_row(str(i), f"{f.score:.4f}", f.kind, text)
        console.print(table)
    emit(
        {
            "query": query,
            "k": k,
            "facts": [{"fact": f.fact, "kind": f.kind, "ts": f.ts, "score": f.score} for f in facts],
        }
    )


@with_agent_mode
def save(
    fact: Annotated[str, typer.Argument(help="The fact to remember.")],
    kind: Annotated[str, typer.Option("--kind", help="preference|entity|decision|constraint|note.")] = "note",
) -> None:
    """Save a durable fact (appends to MEMORY.md + embeds into memory_v1)."""
    from klerk.memory import MemoryFact

    saved = _store().save(MemoryFact(fact=fact, kind=kind))
    console.print(f"[green]Saved[/green] ({saved.kind}): {saved.fact}")
    emit({"fact": saved.fact, "kind": saved.kind, "saved": True})


@with_agent_mode
def show_soul() -> None:
    """Print SOUL.md (seeded with the klerk persona on first run)."""
    soul = _store().read_soul()
    console.print(Panel(soul, title="SOUL.md", border_style="magenta"))
    emit({"soul": soul})


def edit_soul(
    editor: Annotated[str | None, typer.Option("--editor", help="Override $EDITOR.")] = None,
) -> None:
    """Open SOUL.md in $EDITOR (creates + seeds it first if missing)."""
    store = _store()
    store.read_soul()  # ensure seeded + on disk
    chosen = editor or os.environ.get("EDITOR")
    if not chosen:
        console.print(
            f"[yellow]No --editor / $EDITOR set.[/yellow] SOUL.md lives at "
            f"[cyan]{store.soul_path}[/cyan]; edit it directly."
        )
        raise typer.Exit(code=0)
    typer.launch(str(store.soul_path))
    console.print(f"[dim]Opened {store.soul_path} (launched).[/dim]")
