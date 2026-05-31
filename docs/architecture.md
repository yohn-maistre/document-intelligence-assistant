# Architecture

> One tool layer, four surfaces — the Hermes-agent pattern.

## At a glance

```
                   Nemotron proxy — llm-proxy.atlas-horizon.com/v1
                   (private Cloudflare-tunneled LiteLLM, OpenAI-compatible,
                    single-model: nemotron-3-nano-omni)
                          ▲                     ▲                     ▲
                          │                     │ Bahasa fallback     │ stretch
                          │ (CF Access headers) │ (only if separate   │
                          │                     │  KLERK_QWEN_BASE_URL│
                  ┌───────┴────────┐    ┌───────┴────────┐    ┌──────┴─────────┐
                  │ LiteLLM SDK    │    │ Qwen3 / local  │    │ Anthropic /    │
                  │ router + cost  │    │ llama.cpp      │    │ OpenAI fallbk  │
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
| **Typer CLI verbs** | Primary brand. `klerk ask`, `klerk write`, `klerk synth gen`, `klerk eval run`, ... | Humans + agents (`--json`) |
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
| **SQLite checkpoint** | Mid-run resumability for `klerk write` (doc-writer graph) | `.klerk/checkpoints.db` |

LanceDB does double duty: corpus retrieval + semantic LLM cache. One primitive, two roles.

## See also

- [`ASSIGNMENT.md`](./ASSIGNMENT.md) — brief mapping + compliance.
- [`../EVAL.md`](../EVAL.md) — evaluation methodology + results.
- [`../DATA_GENERATION.md`](../DATA_GENERATION.md) — corpus generation + QC.
