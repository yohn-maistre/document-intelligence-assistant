"""MCP gateway — `klerk-mcp` exposes klerk's tool surface over stdio.

Hermes-pattern: one tool layer, multiple surfaces. The MCP server lets any
MCP-aware client (Claude Desktop, Goose, Cursor, Pi, another klerk) call
klerk's verbs without re-implementing them.

Exposed tools (current set; expands as more verbs land):
    search_hybrid       — hybrid retrieve + rerank
    search_bm25         — BM25 only
    search_vector       — dense only
    list_docs           — enumerate corpus doc_ids
    read_chunk          — fetch one chunk by id
    decompose_query     — split a question into atomic sub-questions
    judge_grounding     — score whether evidence covers a question
    ask                 — full CRAG-lite Q&A round
    extract_kg          — extract entities + relations from text
    kg_stats            — current KG node/edge counts
    contradict_scan     — KG contradiction sweep
    draft_doc           — full adversarial multi-drafter doc-writer
    faq_build           — Corpus Learning Agent
    eval_run_rubric     — run the 5-axis rubric over the golden set

Run with: `klerk-mcp` (entry point in pyproject [project.scripts]).
Reviewer connects via Claude Desktop / Goose / Cursor config:
    {"mcpServers": {"klerk": {"command": "klerk-mcp"}}}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server: Server = Server("klerk")


# ─── Tool registry (descriptor + handler) ────────────────────────────────────
def _tools() -> list[Tool]:
    return [
        Tool(
            name="search_hybrid",
            description="Hybrid retrieval over the indexed corpus: vector + BM25 + RRF + BGE-M3 ColBERT rerank. "
                        "Use this for any 'find me relevant passages' need.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
                    "rerank": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_bm25",
            description="BM25 (sparse) search via LanceDB native FTS.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_vector",
            description="Dense vector search via BGE-M3 + LanceDB cosine.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_docs",
            description="Enumerate every doc_id in the indexed corpus.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="read_chunk",
            description="Fetch one chunk by its `<doc_id>:<chunk_idx>` id.",
            inputSchema={
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}},
                "required": ["chunk_id"],
            },
        ),
        Tool(
            name="decompose_query",
            description="Split a complex question into 1-4 atomic sub-questions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "locale": {"type": "string", "enum": ["en", "id"], "default": "en"},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="judge_grounding",
            description="Score 0..1 whether the chunk_ids provided cover the question.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "chunk_ids": {"type": "array", "items": {"type": "string"}},
                    "locale": {"type": "string", "enum": ["en", "id"], "default": "en"},
                },
                "required": ["question", "chunk_ids"],
            },
        ),
        Tool(
            name="ask",
            description="Full CRAG-lite Q&A: decompose → retrieve → judge → correct → answer + cite.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "locale": {"type": "string", "enum": ["en", "id"], "default": "en"},
                    "k": {"type": "integer", "default": 6},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="extract_kg",
            description="Extract entities + relations from a free-text passage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "chunk_id": {"type": "string", "default": "ad-hoc"},
                    "locale": {"type": "string", "enum": ["en", "id"], "default": "en"},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="kg_stats",
            description="Counts: entities, relations, chunks processed.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="contradict_scan",
            description="Pairwise contradiction sweep over the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "locale": {"type": "string", "enum": ["en", "id"], "default": "en"},
                },
            },
        ),
        Tool(
            name="draft_doc",
            description="Adversarial multi-drafter doc-writer. Returns the assembled markdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "n_sections": {"type": "integer", "default": 3, "minimum": 1, "maximum": 8},
                    "k_per_section": {"type": "integer", "default": 8},
                    "locale": {"type": "string", "enum": ["en", "id"], "default": "en"},
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="faq_build",
            description="Corpus Learning Agent: propose + answer FAQ questions per doc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "per_doc": {"type": "integer", "default": 5},
                },
            },
        ),
        Tool(
            name="eval_run_rubric",
            description="Run the 5-axis rubric over the golden set; returns the aggregate scores.",
            inputSchema={
                "type": "object",
                "properties": {
                    "locale": {"type": "string", "enum": ["en", "id"]},
                },
            },
        ),
    ]


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return _tools()


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        result = _dispatch(name, arguments)
    except Exception as e:  # noqa: BLE001
        return [TextContent(type="text", text=json.dumps({"error": f"{type(e).__name__}: {e}"}))]
    return [TextContent(type="text", text=json.dumps(result, default=str, ensure_ascii=False))]


# ─── Dispatch table ──────────────────────────────────────────────────────────
def _dispatch(name: str, args: dict[str, Any]) -> Any:
    if name == "search_hybrid":
        from klerk.rag.retrieve import search_hybrid

        results = search_hybrid(
            args["query"], k_initial=16, k_final=args.get("k", 8), rerank=args.get("rerank", True)
        )
        return [
            {
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "text": r.text,
                "score": r.score,
                "vector_rank": r.vector_rank,
                "bm25_rank": r.bm25_rank,
                "reranked": r.reranked,
            }
            for r in results
        ]

    if name == "search_bm25":
        from klerk.rag.store import search_bm25

        return search_bm25(args["query"], k=args.get("k", 8))

    if name == "search_vector":
        from klerk.rag.embed import embed_query
        from klerk.rag.store import search_vector

        qv = embed_query(args["query"])
        return search_vector(qv, k=args.get("k", 8))

    if name == "list_docs":
        from klerk.rag.store import CORPUS_TABLE, open_db

        db = open_db()
        if CORPUS_TABLE not in db.table_names():
            return []
        rows = db.open_table(CORPUS_TABLE).to_pandas()
        return sorted(rows["doc_id"].unique().tolist())

    if name == "read_chunk":
        from klerk.rag.store import CORPUS_TABLE, open_db

        db = open_db()
        if CORPUS_TABLE not in db.table_names():
            return None
        rows = db.open_table(CORPUS_TABLE).to_pandas()
        match = rows[rows["chunk_id"] == args["chunk_id"]]
        if match.empty:
            return None
        row = match.iloc[0].to_dict()
        row.pop("vector", None)  # don't ship 1024-float vectors over MCP
        return row

    if name == "decompose_query":
        from klerk.agent.crag import decompose_query

        return decompose_query(args["question"], locale=args.get("locale", "en")).model_dump()

    if name == "judge_grounding":
        from klerk.agent.crag import judge_grounding
        from klerk.agent.schemas import Chunk
        from klerk.rag.store import CORPUS_TABLE, open_db

        db = open_db()
        table = db.open_table(CORPUS_TABLE)
        rows = table.to_pandas()
        chunks = []
        for cid in args["chunk_ids"]:
            m = rows[rows["chunk_id"] == cid]
            if not m.empty:
                r = m.iloc[0].to_dict()
                chunks.append(
                    Chunk(
                        chunk_id=r["chunk_id"],
                        doc_id=r["doc_id"],
                        text=r["text"],
                        locale=r.get("locale", "und"),
                        source=r.get("source", ""),
                        score=0.0,
                    )
                )
        return judge_grounding(args["question"], chunks, locale=args.get("locale", "en")).model_dump()

    if name == "ask":
        from klerk.agent.crag import ask as crag_ask

        trace = crag_ask(args["question"], locale=args.get("locale", "en"), k_final=args.get("k", 6))
        return {
            "answer": trace.answer.answer,
            "citations": trace.answer.citations,
            "confidence": trace.answer.confidence,
            "locale": trace.answer.locale,
            "sub_questions": trace.sub_questions,
        }

    if name == "extract_kg":
        from klerk.agent.kg_extract import extract_chunk

        return extract_chunk(
            args.get("chunk_id", "ad-hoc"),
            args["text"],
            locale=args.get("locale", "en"),
        ).model_dump()

    if name == "kg_stats":
        from klerk.agent.kg_extract import stats

        s = stats()
        return {"entities": s.n_entities, "relations": s.n_relations, "chunks_seen": s.n_chunks_seen}

    if name == "contradict_scan":
        from klerk.agent.contradiction import render_report, scan

        findings = scan(locale=args.get("locale", "en"))
        return {"n_findings": len(findings), "report_md": render_report(findings)}

    if name == "draft_doc":
        from klerk.agent.doc_writer import propose, save_proposal

        p = propose(
            args["topic"],
            n_sections=args.get("n_sections", 3),
            k_per_section=args.get("k_per_section", 8),
            locale=args.get("locale", "en"),
        )
        path = save_proposal(p)
        return {"path": str(path), "markdown": p.to_markdown()}

    if name == "faq_build":
        from klerk.agent import faq as faq_mod

        entries = faq_mod.build(per_doc_q_cap=args.get("per_doc", 5))
        path = faq_mod.save(entries)
        return {"n_entries": len(entries), "path": str(path)}

    if name == "eval_run_rubric":
        from klerk.eval.golden import load
        from klerk.eval.rubric import aggregate, run

        items = load(locale=args.get("locale"))
        results = run(items)
        return {"aggregate": aggregate(results), "n_items": len(results)}

    raise ValueError(f"unknown tool: {name}")


async def _amain() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Entry point exposed via [project.scripts] klerk-mcp = ..."""
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
