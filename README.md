# klerk

> **Document Intelligence Assistant** — multi-agent RAG over your documents.
> Hybrid retrieval, knowledge-graph extraction, adversarial proposal pipeline,
> custom 5-axis eval rubric, polished operator TUI. One tool layer, four
> surfaces.

Take-home for the **Middle AI Engineer** role at **PT Fata Organa Solusi** (Indonesian voice/audio AI + SaaS), planned **2026-05-28**.

## 30-second demo

```bash
# 1. install (uv + pnpm, ~3 min on cold cache)
make setup

# 2. set your Nemotron key
cp .env.example .env  &&  $EDITOR .env   # NVIDIA_API_KEY=...

# 3. end-to-end on the seed corpus (3 hand-authored docs, 40% Bahasa)
make demo

# 4. eval (RAGAS + 5-axis rubric + SEA-HELM-style Bahasa parity)
make eval

# 5. operator panel
make studio
```

To run klerk on your own documents: drop them into `data/raw/` and re-run `klerk index build`. Drive ingestion is supported but optional (`klerk drive pull --folder <id>`).

## Four surfaces, one backend

```
                   Nemotron NIM  ←→  Qwen3 (--locale id)  ←→  fallbacks (stretch)
                          ▲
                          │  via LiteLLM SDK (in-process, fallbacks + cost + cache)
                          │  + DiskCache exact + LanceDB semantic cache + Pydantic AI
                          │
            ┌─────────────┴─────────────────────────────────────────┐
            │   TOOL SURFACE  (Python; 14 tools)                    │
            │   search_hybrid · rerank_bge · decompose · judge      │
            │   list_docs · read_chunk · extract_kg · contradict    │
            │   propose · adjudicate_drafts · score_rubric          │
            │   anomaly_scan · faq_build · trace_citations          │
            └─┬──────────┬───────────┬──────────────┬───────────────┘
              │          │           │              │
        ┌─────▼──────┐ ┌─▼────┐ ┌────▼────────┐ ┌───▼─────────┐
        │ Typer CLI  │ │ klerk│ │ klerk-mcp   │ │ FastAPI+SSE │
        │ + Rich     │ │ -cli │ │ MCP gateway │ │ (stub for   │
        │ (PRIMARY)  │ │ chat │ │ (stdio)     │ │  web hook)  │
        └────────────┘ └──────┘ └─────────────┘ └─────────────┘
                                       │
                          ┌────────────┴────────────┐
                          │   klerk studio          │
                          │   5-panel Textual TUI   │
                          │   (read-only operator)  │
                          └─────────────────────────┘
```

| Surface | Who uses it | How |
|---|---|---|
| **CLI verbs** (the headline brand) | Humans + agents | `uv run klerk ask "..."` · `uv run klerk propose "..."` · `--json` for agents |
| **klerk-cli chat** | Humans | `klerk chat` — Pi runs hidden underneath; never appears in any output |
| **MCP gateway** | Other agents | `klerk-mcp` (stdio); Claude Desktop / Goose / Cursor / Pi point at it |
| **Studio TUI** | Operators | `klerk studio` — 5 panels (corpus / eval / traces / proposals / KG) |

LanceDB does double duty: corpus retrieval AND the semantic LLM cache live in the same vector primitive. One primitive, two roles. See `docs/design-decisions.md` for the full rationale.

## What klerk does

**MUST tier** (shipped):

1. **Hybrid retrieval + reranking** — LanceDB native (vector + Tantivy BM25) + hand-rolled RRF (`rag/fusion.py`) + BGE-Reranker-v2-m3 cross-encoder
2. **Q&A with citations** (`klerk ask`) — CRAG-lite: decompose → retrieve → rerank → judge → correct (≤1 round) → answer with `[doc:chunk]`
3. **Adversarial proposal pipeline** (`klerk propose`) — 7 stages: Researcher → Scope → **Drafter-A ‖ Drafter-B** → Citation Tracer → **Adjudicator** → Critic. The Dynamic-Workflows extract: parallel drafters compete, adjudicator picks winner, critic scores against the 5-axis rubric.
4. **Knowledge graph** (`klerk kg extract`) — Pydantic AI structured outputs → NetworkX (DIY; not GraphRAG / LightRAG / HippoRAG 2; see design-decisions for the cost analysis)
5. **Contradiction report** (`klerk contradict scan`) — pairwise scan over KG entities, surfaces "Doc A says X, Doc B says ¬X"
6. **Auto-FAQ** (`klerk faq build`) — Corpus Learning Agent generates its own questions per doc + answers them via CRAG
7. **Two-layer LLM cache** — DiskCache (exact) + LanceDB `llm_cache` table (semantic, cosine > 0.95)
8. **Replay via cache + Phoenix** — re-run identical prompts hits cache deterministically; Phoenix preserves all spans
9. **Arize Phoenix** observability (embedded SQLite, OpenInference / OpenTelemetry standard; replaces Langfuse-the-6-container-Compose-stack)
10. **RAGAS + custom 5-axis rubric + SEA-HELM-style Bahasa parity** (`klerk eval run`)
11. **Bahasa-heavy seed corpus** (40% Bahasa across 3 hand-authored docs with cross-doc seeded facts for multi-hop probes)
12. **klerk-cli chat shell** (Ink banner / help / version; delegates to Pi as a hidden runtime)
13. **MCP gateway** (`klerk-mcp`, 14 tools over stdio)
14. **`@yohnmaistre/pi-extension-klerk` npm package** (publishable; makes us a Pi *contributor*)
15. **`docs/design-decisions.md`** — every framework choice + every runner-up rejected, with Anthropic citations as the spine

**SHOULD tier** (shipped):

16. **Textual Studio TUI** — `klerk studio`, 5 panels
17. **Background Ingestion Agent** — `klerk bg start | status` (APScheduler, no Cognee/Letta/mem0 dep)
18. **Mid-run resumability** — SQLite checkpoint store (`klerk trace list`)
19. **Anomaly detection** — `klerk anomaly scan` (z-score on doc-centroid distance + LLM justification)
20. **KG visualization** — `klerk kg viz` (pyvis HTML; static fallback)
21. **PageRank tiebreaker** — `rag/pagerank.py` (the HippoRAG 2 *idea* extracted; ~80 LOC; no framework)

**STRETCH tier** (documented + scripts shipped, integration deferred):

26. **Local LLM** — `scripts/setup-local-llm.sh` builds llama.cpp + downloads Gemma 3 E4B-IT (or Qwen 3.5/3.6 small), serves on :8080 (OpenAI-compatible). PDP Law 2026 local-inference story.

Items 22-25, 27-28 (adversarial query agent, drift detection, textual-web browser deploy, FastAPI+SSE web hook, Dynamic-Workflows-v1 LLM-writes-orchestration experiment, Cognee MCP swap) — documented in `docs/design-decisions.md` and `docs/2026-landscape.md` as the migration paths; not implemented.

## Verb reference

```bash
# ─── ingestion ──────────────────────────────────────────────────────────────
klerk drive pull --folder <id> --out data/raw/    # optional (service-acct)
klerk parse <path>                                 # Docling / PyMuPDF / native
klerk index build --src data/seed --rebuild        # parse + chunk + embed + upsert
klerk index stats                                  # corpus stats

# ─── retrieval ──────────────────────────────────────────────────────────────
klerk search bm25   "<q>" -k 8                     # LanceDB native FTS
klerk search vector "<q>" -k 8                     # BGE-M3 + LanceDB cosine
klerk search hybrid "<q>" -k 8 [--no-rerank]       # RRF + BGE-Reranker

# ─── Q&A / proposal / FAQ / contradiction ───────────────────────────────────
klerk ask    "<q>" [--locale en|id] [--trace] [--no-correct]
klerk propose "<topic>" -n 3 [--locale en|id]      # adversarial pipeline
klerk faq build [--per-doc 5]                      # Corpus Learning Agent
klerk contradict scan [--locale en|id]             # pairwise KG sweep

# ─── KG ─────────────────────────────────────────────────────────────────────
klerk kg extract [--rebuild]                       # Pydantic AI → NetworkX
klerk kg stats
klerk kg show [--entity ID] [--limit 20]
klerk kg viz [--out PATH]                          # pyvis HTML

# ─── anomaly + background ───────────────────────────────────────────────────
klerk anomaly scan [--sigma 2.0] [--locale en|id]
klerk bg start [--interval 60] [--once]            # APScheduler watch loop
klerk bg status                                    # last cycle report

# ─── eval ───────────────────────────────────────────────────────────────────
klerk eval run [--ragas/--no-ragas] [--rubric/--no-rubric] [--seahelm/--no-seahelm]
                [--locale en|id]

# ─── surfaces ───────────────────────────────────────────────────────────────
klerk chat                                         # via klerk-cli (TS shell)
klerk-mcp                                          # MCP server (stdio)
klerk studio [--serve]                             # Textual TUI
klerk trace list [--op NAME] [--limit 20]          # checkpoint runs

# ─── observability ──────────────────────────────────────────────────────────
klerk smoke                                        # h0 LiteLLM + Phoenix check
```

## Architecture & engineering log

| Doc | What's in it |
|---|---|
| [docs/architecture.md](./docs/architecture.md) | ASCII diagram + Hermes-pattern notes + the 4-surface story |
| [docs/design-decisions.md](./docs/design-decisions.md) | Every framework pick, every runner-up rejected, with Anthropic *Building Effective Agents* + *Dynamic Workflows* (May 2026) as the spine |
| [docs/2026-landscape.md](./docs/2026-landscape.md) | The May 2026 field map — LightRAG / HippoRAG 2 / GraphRAG / Cognee / Langfuse / Pi / Hermes / Goose / Mastra |
| [docs/proposal-rubric.md](./docs/proposal-rubric.md) | The 5-axis custom rubric methodology |
| [docs/bahasa-eval.md](./docs/bahasa-eval.md) | SEA-HELM-style Bahasa parity methodology + PDP Law 2026 |

## MCP — agent-to-agent

`klerk-mcp` exposes 14 tools over stdio. Any MCP-aware client can drive klerk:

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json` or equivalent):

```json
{
  "mcpServers": {
    "klerk": {
      "command": "klerk-mcp"
    }
  }
}
```

Then in any Claude chat: *"Use klerk's `propose` tool to draft a 3-section project brief for Pelangi's IP-clause renegotiation."*

Goose, Cursor, and Pi work the same way. The Pi extension `@yohnmaistre/pi-extension-klerk` (in `pi-extension-klerk/`) pre-registers klerk's skills if you'd rather ship them with a Pi instance.

## Stack

| Layer | Pick |
|---|---|
| Chat harness | klerk-cli (TS, Ink) + Pi as hidden runtime |
| Orchestration | Hand-rolled (`agent/crag.py`, `agent/proposal_pipeline.py`); no LangGraph |
| LLM gateway | LiteLLM SDK (in-process); Nemotron NIM + Qwen3 (Bahasa) + optional fallbacks |
| Vector + BM25 | LanceDB native hybrid (Tantivy FTS, March 2026) |
| Embeddings | BGE-M3 (multilingual, self-hosted) |
| Reranker | BGE-Reranker-v2-m3 (cross-encoder) |
| Knowledge graph | NetworkX in-memory + JSON; Pydantic AI extraction |
| Cache | DiskCache (exact) + LanceDB `llm_cache` (semantic) |
| Observability | Arize Phoenix (SQLite-backed, OpenInference) |
| Parsing | Docling 2.72+ primary; PyMuPDF fallback |
| Background ingestion | APScheduler + asyncio (no Cognee / Letta / mem0) |
| Studio | Textual |
| Eval | RAGAS + custom 5-axis rubric + SEA-HELM-style Bahasa |
| MCP | Python `mcp` SDK over stdio |

See `docs/design-decisions.md` for the *why* of every line above.

## Quickstart for the reviewer

```bash
# clone + install
git clone https://github.com/yohn-maistre/document-intelligence-assistant
cd document-intelligence-assistant
make setup

# point at your Nemotron
cp .env.example .env  &&  $EDITOR .env

# index the bundled seed corpus (3 docs, 40% Bahasa, cross-doc facts seeded)
uv run klerk index build --src data/seed --rebuild

# extract a KG, scan for contradictions, build an FAQ
uv run klerk kg extract --rebuild
uv run klerk contradict scan
uv run klerk faq build

# adversarial proposal
uv run klerk propose "Q1 budget variance — consultant spend + parental leave coverage" -n 3

# eval
uv run klerk eval run
cat data/output/eval/rubric.json | jq '.aggregate'

# operator TUI
uv run klerk studio

# MCP gateway (for Claude Desktop / Goose / Cursor / Pi)
uv run klerk-mcp
```

## Demo queries (canned, against the seed corpus)

| Mode | Query | What it exercises |
|---|---|---|
| Bahasa single-doc | `klerk ask "Berapa tarif konsultan advisory PT Pelangi per jam?" --locale id` | Bahasa retrieval + citation |
| EN multi-hop | `klerk ask "Why did Q1 consultant spend overrun by 29% — was it rate or volume?"` | Multi-hop across HR policy + memo + contract |
| CRAG trigger | `klerk ask "What's the contingency budget recommendation?"` | Underspecified — forces a corrective re-query |
| Adversarial proposal | `klerk propose "Pelangi IP-clause renegotiation" -n 3` | Drafter-A vs Drafter-B → Adjudicator → Critic |
| Anomaly | drop a non-fit doc into `data/raw/`, then `klerk bg start --once && klerk anomaly scan` | Outlier detection + LLM justification |

## License

MIT — see `pyproject.toml`. Pi (`@mariozechner/pi-coding-agent`) is its own thing; we depend on it via npm.

## Acknowledgements

- **Anthropic** — *Building Effective Agents* and *Dynamic Workflows* (May 2026) shape the entire stance behind klerk (own the loop, frameworks are commoditized, adversarial subagent verification).
- **Mario Zechner** — Pi (`@mariozechner/pi-coding-agent`) gives klerk its chat TUI without a rewrite.
- **NousResearch (Hermes Agent)** — the architectural pattern klerk copies (one tool layer, four surfaces, MCP as gateway).
- **Cognee, LightRAG, HippoRAG 2, GraphRAG** — the production-scale answers klerk is a slimmer version of; see `docs/design-decisions.md` for the per-framework analysis.
- **Singapore AI (SEA-HELM)** — the methodology klerk's Bahasa parity report extracts.
