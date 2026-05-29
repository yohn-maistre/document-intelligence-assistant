"""`klerk search {bm25,vector,hybrid} <query>` — exercise retrieval directly."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from klerk.rag.embed import embed_query
from klerk.rag.retrieve import search_hybrid
from klerk.rag.store import search_bm25, search_vector

console = Console()

MAX_PREVIEW_CHARS = 220


def _preview(text: str) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > MAX_PREVIEW_CHARS:
        text = text[:MAX_PREVIEW_CHARS] + "…"
    return text


def bm25(
    query: Annotated[str, typer.Argument(help="Query string.")],
    k: Annotated[int, typer.Option("--k", "-k")] = 8,
) -> None:
    """BM25 search via LanceDB native FTS."""
    hits = search_bm25(query, k=k)
    _render(hits, title=f"BM25 ({len(hits)} hits)")


def vector(
    query: Annotated[str, typer.Argument(help="Query string.")],
    k: Annotated[int, typer.Option("--k", "-k")] = 8,
) -> None:
    """Vector search via BGE-M3 query embedding + LanceDB cosine."""
    qv = embed_query(query)
    hits = search_vector(qv, k=k)
    _render(hits, title=f"Vector ({len(hits)} hits)")


def hybrid(
    query: Annotated[str, typer.Argument(help="Query string.")],
    k: Annotated[int, typer.Option("--k", "-k")] = 8,
    initial: Annotated[int, typer.Option("--initial", help="Candidates before rerank.")] = 16,
    no_rerank: Annotated[bool, typer.Option("--no-rerank", help="Skip ColBERT rerank step.")] = False,
) -> None:
    """Hybrid: vector + BM25 → RRF → BGE-M3 ColBERT MaxSim rerank."""
    results = search_hybrid(query, k_initial=initial, k_final=k, rerank=not no_rerank)

    table = Table(
        title=f"Hybrid retrieval — {len(results)} result(s){' (reranked)' if not no_rerank else ''}",
        border_style="green",
    )
    table.add_column("#", style="dim", justify="right")
    table.add_column("chunk_id", style="cyan")
    table.add_column("score", justify="right")
    table.add_column("v", style="dim", justify="right")
    table.add_column("b", style="dim", justify="right")
    table.add_column("locale", style="dim")
    table.add_column("preview")
    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.chunk_id,
            f"{r.score:.4f}",
            str(r.vector_rank) if r.vector_rank else "—",
            str(r.bm25_rank) if r.bm25_rank else "—",
            r.locale,
            _preview(r.text),
        )
    console.print(table)


def _render(hits: list[dict], *, title: str) -> None:
    table = Table(title=title, border_style="cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("chunk_id", style="cyan")
    table.add_column("doc_id", style="dim")
    table.add_column("locale", style="dim")
    table.add_column("preview")
    for i, h in enumerate(hits, 1):
        table.add_row(
            str(i),
            h.get("chunk_id", "?"),
            h.get("doc_id", "?"),
            h.get("locale", "?"),
            _preview(h.get("text", "")),
        )
    console.print(table)
