"""BONUS pane — top-10 KG entities by degree.

Loads the persisted NetworkX graph (``klerk.agent.kg_extract.load_graph``)
and renders the ten highest-degree entities with their relation counts in a
DataTable. Best-effort: an empty / absent graph renders a hint.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

_TOP_N = 10


def _top_entities() -> list[tuple[str, str, int]]:
    """Return (entity, type, degree) for the top-N entities by degree."""
    try:
        from klerk.agent.kg_extract import load_graph

        g = load_graph()
    except Exception:  # noqa: BLE001 — kg deps / file optional
        return []
    if g.number_of_nodes() == 0:
        return []
    ranked = sorted(g.degree, key=lambda kv: kv[1], reverse=True)[:_TOP_N]
    out: list[tuple[str, str, int]] = []
    for node, degree in ranked:
        attrs = g.nodes[node]
        etype = attrs.get("type") or attrs.get("entity_type") or "?"
        out.append((str(node), str(etype), int(degree)))
    return out


class KgSnapshot(Container):
    """Top-10 entities + relation counts."""

    DEFAULT_CSS = """
    KgSnapshot {
        height: 1fr;
        border: round $primary;
        border-title-color: $primary;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = "knowledge graph"
        rows = _top_entities()
        if not rows:
            yield Static(
                "[dim]No KG yet — run [cyan]klerk kg extract[/cyan].[/dim]"
            )
            return
        table: DataTable[str] = DataTable(cursor_type="row", zebra_stripes=True)
        table.add_columns("entity", "type", "degree")
        for entity, etype, degree in rows:
            table.add_row(entity[:32], etype, str(degree))
        yield table
