"""`klerk kg extract|stats|show` — build, inspect, dump the knowledge graph."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from klerk.agent import kg_extract
from klerk.cli._agent_flag import agent_console, emit, with_agent_mode

console = agent_console()


@with_agent_mode
def extract(
    rebuild: Annotated[bool, typer.Option("--rebuild", help="Drop existing graph first.")] = False,
) -> None:
    """Extract a KG from every chunk in the LanceDB corpus."""
    if rebuild:
        from pathlib import Path

        path = kg_extract._kg_path()  # noqa: SLF001
        if path.exists():
            path.unlink()
            console.print(f"[dim]dropped {path}[/dim]")

    try:
        stats_ = kg_extract.rebuild_from_corpus()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    table = Table(title="KG built", border_style="green")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("entities", str(stats_.n_entities))
    table.add_row("relations", str(stats_.n_relations))
    table.add_row("chunks processed", str(stats_.n_chunks_seen))
    console.print(table)
    emit(
        {
            "entities": stats_.n_entities,
            "relations": stats_.n_relations,
            "chunks_seen": stats_.n_chunks_seen,
        }
    )


@with_agent_mode
def stats() -> None:
    """Print current KG stats."""
    s = kg_extract.stats()
    if s.n_entities == 0 and s.n_relations == 0:
        console.print("[yellow]Graph is empty — run `klerk kg extract` first.[/yellow]")
        emit({"entities": 0, "relations": 0, "chunks_seen": 0, "empty": True})
        raise typer.Exit(code=0)
    table = Table(title="KG stats", show_header=False, border_style="dim")
    table.add_column("metric", style="dim")
    table.add_column("value")
    table.add_row("entities", str(s.n_entities))
    table.add_row("relations", str(s.n_relations))
    table.add_row("chunks seen", str(s.n_chunks_seen))
    console.print(table)
    emit(
        {
            "entities": s.n_entities,
            "relations": s.n_relations,
            "chunks_seen": s.n_chunks_seen,
            "empty": False,
        }
    )


def show(
    entity: Annotated[str | None, typer.Option("--entity", "-e", help="Filter to one entity id.")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
) -> None:
    """Print entities + their out-edges."""
    g = kg_extract.load_graph()
    if g.number_of_nodes() == 0:
        console.print("[yellow]Graph is empty.[/yellow]")
        raise typer.Exit(code=0)

    if entity:
        if not g.has_node(entity):
            console.print(f"[red]Unknown entity: {entity}[/red]")
            raise typer.Exit(code=1)
        nodes = [entity]
    else:
        nodes = list(g.nodes())[:limit]

    for node_id in nodes:
        attrs = g.nodes[node_id]
        body_lines = [
            f"[bold]type[/bold]: {attrs.get('type', '?')}",
            f"[bold]name[/bold]: {attrs.get('name', '?')}",
            f"[bold]aliases[/bold]: {', '.join(sorted(attrs.get('aliases', []))) or '—'}",
        ]
        ev = sorted(attrs.get("evidence_chunks", []))
        if ev:
            body_lines.append(f"[bold]evidence_chunks[/bold]: {', '.join(ev)}")
        out_edges = list(g.out_edges(node_id, keys=True, data=True))
        if out_edges:
            body_lines.append("[bold]relations[/bold]:")
            for _, tgt, _, edata in out_edges:
                body_lines.append(
                    f"  → {tgt}  [dim]({edata['verb']}; ev={edata['evidence_chunk']})[/dim]"
                )
        console.print(Panel("\n".join(body_lines), title=node_id, border_style="cyan"))
