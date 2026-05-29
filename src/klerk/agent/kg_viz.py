"""Knowledge graph visualization — pyvis HTML export from NetworkX.

`klerk kg viz` renders the persisted KG to a standalone HTML file the
operator can open in a browser. Pyvis (vis.js wrapper) is the lightest
zero-server option in 2026 — no React, no D3 bundle.

The Studio TUI's KG panel embeds a screenshot of this same HTML for the
operator-TUI workflow.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx


_TYPE_COLOURS = {
    "organization": "#4A90E2",
    "person":       "#E27D60",
    "policy":       "#85DCB0",
    "contract":     "#E8A87C",
    "date":         "#C38D9E",
    "money":        "#F2D74E",
    "identifier":   "#9C9CFB",
    "location":     "#88D8B0",
    "concept":      "#FF8B94",
    "other":        "#AAAAAA",
}


def render_html(g: nx.MultiDiGraph, out_path: Path) -> Path:
    """Render `g` to an interactive HTML file. Returns the path."""
    try:
        from pyvis.network import Network
    except ImportError:
        # Pyvis isn't a MUST-tier dependency — emit a static fallback so the
        # verb still produces *something* without bombing.
        return _render_static_fallback(g, out_path)

    net = Network(
        height="780px",
        width="100%",
        bgcolor="#0f1115",
        font_color="#e6e6e6",
        notebook=False,
        directed=True,
    )
    net.barnes_hut()

    for node_id, attrs in g.nodes(data=True):
        ntype = attrs.get("type", "other")
        colour = _TYPE_COLOURS.get(ntype, _TYPE_COLOURS["other"])
        aliases = sorted(attrs.get("aliases", []))
        evidence = sorted(attrs.get("evidence_chunks", []))
        title = (
            f"<b>{attrs.get('name', node_id)}</b><br>"
            f"<i>{ntype}</i><br>"
            + (f"aliases: {', '.join(aliases)}<br>" if aliases else "")
            + (f"evidence: {', '.join(evidence[:6])}" if evidence else "")
        )
        net.add_node(node_id, label=attrs.get("name", node_id), title=title, color=colour)

    for u, v, edata in g.edges(data=True):
        verb = edata.get("verb", "")
        evidence = edata.get("evidence_chunk", "")
        net.add_edge(u, v, title=f"{verb}<br>{evidence}", label=verb)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out_path), notebook=False, open_browser=False)
    return out_path


def _render_static_fallback(g: nx.MultiDiGraph, out_path: Path) -> Path:
    """Pyvis-less fallback: a minimal HTML table listing nodes + edges."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "<!doctype html><html><head><meta charset='utf-8'><title>klerk KG (static)</title>",
        "<style>body{font-family:system-ui;background:#0f1115;color:#e6e6e6;padding:24px;}",
        "table{border-collapse:collapse;margin:16px 0;}td,th{border:1px solid #333;padding:6px 10px;}",
        "h1,h2{color:#9C9CFB;}</style></head><body>",
        "<h1>klerk knowledge graph (static fallback — install pyvis for interactive)</h1>",
        f"<p>{g.number_of_nodes()} entities · {g.number_of_edges()} relations</p>",
        "<h2>Entities</h2><table><tr><th>id</th><th>type</th><th>name</th><th>aliases</th></tr>",
    ]
    for node_id, attrs in g.nodes(data=True):
        lines.append(
            f"<tr><td>{node_id}</td><td>{attrs.get('type', '?')}</td>"
            f"<td>{attrs.get('name', '?')}</td>"
            f"<td>{', '.join(sorted(attrs.get('aliases', [])))}</td></tr>"
        )
    lines.append("</table><h2>Relations</h2><table><tr><th>source</th><th>verb</th><th>target</th><th>evidence_chunk</th></tr>")
    for u, v, edata in g.edges(data=True):
        lines.append(
            f"<tr><td>{u}</td><td>{edata.get('verb', '?')}</td>"
            f"<td>{v}</td><td>{edata.get('evidence_chunk', '?')}</td></tr>"
        )
    lines.append("</table></body></html>")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
