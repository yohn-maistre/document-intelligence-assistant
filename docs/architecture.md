# Architecture

> One tool layer, four surfaces — the Hermes-agent pattern.

## At a glance

```
                   Nemotron NIM (integrate.api.nvidia.com/v1, OpenAI-compatible)
                          ▲                     ▲                     ▲
                          │                     │ Bahasa fallback     │ stretch
                  ┌───────┴────────┐    ┌───────┴────────┐    ┌──────┴─────────┐
                  │ LiteLLM SDK    │    │ Qwen3 (NIM/HF) │    │ Anthropic /    │
                  │ router + cost  │    │ when --locale id│   │ OpenAI fallbk  │
                  └───────┬────────┘    └────────────────┘    └────────────────┘
                          │
                          │ + DiskCache (exact) + LanceDB llm_cache (semantic)
                          │ + Pydantic AI (structured tool outputs)
                          │ + Arize Phoenix (OpenInference / OTel traces)
                          │
            ┌─────────────┴───────────────────────────────────────┐
            │   TOOL SURFACE (Python functions)                   │
            │   search_hybrid · rerank_bge · decompose · judge    │
            │   list_docs · read_chunk · extract_kg · contradict  │
            │   propose_section · adjudicate_drafts · score_rubric│
            │   anomaly_scan · faq_build · trace_citations        │
            └─┬──────────┬───────────┬──────────────┬─────────────┘
              │          │           │              │
   ┌──────────▼──┐ ┌─────▼────┐ ┌────▼───────┐ ┌────▼──────────┐
   │ klerk-cli   │ │ Typer    │ │ MCP server │ │ FastAPI + SSE │
   │ Ink shell   │ │ verbs    │ │ (stdio)    │ │ (web hook)    │
   │ Pi hidden   │ │ + Rich   │ │ Hermes-pat │ │ stub for now  │
   └─────────────┘ └──────────┘ └────────────┘ └───────────────┘
                          ▲
                          │
   ┌──────────────────────┴────────────────────────────────────┐
   │  Textual Studio TUI — 5 panels                            │
   │  Corpus · Eval · Traces · Proposals · KG                  │
   └───────────────────────────────────────────────────────────┘
```

## The four surfaces

| Surface | Role | Who uses it |
|---|---|---|
| **Typer CLI verbs** | Primary brand. `klerk ask`, `klerk propose`, `klerk synth gen`, `klerk eval run`, ... | Humans + agents (`--json`) |
| **klerk-cli chat shell** | Ink-wrapped chat REPL; Pi runs hidden underneath | Humans |
| **MCP gateway** (`klerk-mcp`) | Stdio MCP server exposing the tool surface | Other agents (Claude Desktop, Goose, Cursor, another Pi) |
| **Studio TUI** (`klerk studio`) | Textual operator panel; 5 panels | Operators / debugging |

## The four storage primitives

| Primitive | What it holds | Where |
|---|---|---|
| **LanceDB (corpus table)** | Document chunks + BGE-M3 embeddings; hybrid query via Tantivy BM25 + vector RRF | `.lancedb/corpus.lance` |
| **LanceDB (`llm_cache` table)** | Prompt embedding → cached response (semantic cache, sim > 0.95) | `.lancedb/llm_cache.lance` |
| **NetworkX KG (JSON)** | Entities + relations extracted via Pydantic AI structured output | `data/kg/graph.json` |
| **Phoenix SQLite** | OpenInference traces; powers the Studio Trace panel + replay | `.phoenix/phoenix.db` |
| **DiskCache** | Exact-match LLM cache (prompt hash → response) | `.diskcache/` |
| **SQLite checkpoint** | Mid-run resumability for `klerk propose` | `.klerk/checkpoints.db` |

LanceDB does double duty: corpus retrieval + semantic LLM cache. One primitive, two roles.

## See also

- [`design-decisions.md`](./design-decisions.md) — every framework pick + every runner-up rejected, with the Anthropic citations as the spine.
- [`proposal-rubric.md`](./proposal-rubric.md) — the custom 5-axis rubric calibration set.
- [`bahasa-eval.md`](./bahasa-eval.md) — SEA-HELM-style Bahasa methodology.
- [`2026-landscape.md`](./2026-landscape.md) — LightRAG / HippoRAG 2 / GraphRAG / Pi / Hermes / Goose references, including Anthropic's *Dynamic Workflows* (May 2026).
