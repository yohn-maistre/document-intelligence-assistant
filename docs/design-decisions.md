# klerk — Design Decisions

> Every framework we picked, every framework we rejected, and why. This doc is
> the engineering log; the README is the elevator pitch.

## Opening — the principle

Two passages from Anthropic's *Building Effective Agents* (Dec 2024, updated 2026) set the bar for every choice on this page:

> *"Consistently, the most successful implementations weren't using complex frameworks or specialized libraries. Instead, they were building with simple, composable patterns."*

> *"We suggest that developers start by using LLM APIs directly: many patterns can be implemented in a few lines of code. If you do use a framework, ensure you understand the underlying code."*

— Anthropic, [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)

Anthropic's own Claude Code uses a deliberately simple single-threaded master loop. klerk is built in that spirit: own the loop, justify every dependency, hand-roll the critical paths. The five SOTA frameworks we considered (LangGraph, Langfuse, GPTCache, HippoRAG 2, LightRAG, Cognee) are *all* defensible at production scale — but at the scale of a take-home (25-doc corpora, single-tenant, one reviewer machine) they would replace work that's better hand-rolled.

The May 2026 *Dynamic Workflows* paradigm (Claude Code, Opus 4.8) reinforces this stance rather than contradicting it: Dynamic Workflows is not framework adoption — it's *the LLM itself writing the orchestration code per task at runtime*. klerk extracts the spirit (parallel adversarial subagents in the proposal pipeline, runtime-memory-style structured tool outputs, SQLite-backed resumability) without taking on the runtime code-generation risk.

## Stack — what we picked and why

| Layer | Pick | One-line rationale |
|---|---|---|
| Chat harness | `klerk-cli` (TS, Ink banner) + Pi as hidden runtime | The brand identity is ours; Pi gives us a diff-rendered TUI for free. |
| Orchestration | Hand-rolled ReAct + CRAG-lite loop in Python (~200 LOC) | Anthropic stance. Loop ownership = system ownership. |
| LLM gateway | LiteLLM SDK (in-process, not proxy) | One library = fallbacks + cost tracking + cache hooks, no extra process. |
| Vector + BM25 | LanceDB native hybrid (Tantivy FTS) | Embedded, no Docker, March 2026 hybrid one-call API. |
| Embeddings | BGE-M3 (self-hosted, sentence-transformers) | Multilingual; Bahasa-strong; no API-key dependency for the reviewer's first run. |
| Reranker | BGE-Reranker-v2-m3 (cross-encoder, self-hosted) | 50-100ms CPU latency; clear quality lift over RRF-alone. |
| Knowledge graph | NetworkX (in-memory + JSON persist) | Kùzu archived; Memgraph license-locked; Neo4j too heavy. |
| KG extraction | Pydantic AI structured outputs → NetworkX | $10-50 cost on 25 docs vs $100+ for Microsoft GraphRAG. |
| LLM cache (exact) | DiskCache (SQLite-backed) | Prod-grade, Apache-2.0, ~1 KB/entry, no server. |
| LLM cache (semantic) | LanceDB `llm_cache` table | Same vector primitive does double duty (retrieval + cache). |
| Observability | Arize Phoenix (embedded SQLite + OpenInference) | Standards-based, runs locally with `phoenix.launch()`, no Docker. |
| Parsing | Docling 2.72+ primary; PyMuPDF fallback | IBM/Linux Foundation backed; PyMuPDF guard for torch/easyocr install issues. |
| Background ingestion | APScheduler + asyncio (~80 LOC, no framework) | Highest-ROI 2026 async pattern for doc intelligence. |
| Studio TUI | Textual | Embedded, no server. `textual serve` for STRETCH browser deploy. |
| Eval | RAGAS baseline + custom 5-axis rubric + SEA-HELM-style Bahasa parity | RAGAS for credibility; custom rubric is the differentiator. |
| MCP gateway | Python `mcp` SDK over stdio | One server, four agent clients (Claude Desktop / Goose / Cursor / Pi). |

## Frameworks we rejected — and how klerk extracts their ideas

### LangGraph

**What it is**: state-machine framework for stateful, looping agents. v2.0 (Feb 2026), 90M monthly downloads, deployed at Uber / JP Morgan / Klarna.

**Why we didn't adopt it**: in a take-home it signals *defaulted to scaffolding*. Anthropic's stance is explicit. Claude Code itself uses a single-threaded master loop. We hand-rolled klerk's loop (`agent/crag.py`, ~150 LOC) so a reviewer can read every state transition.

**What we extracted**: the *idea* of a typed agent state machine. Our `agent/proposal_pipeline.py` flow (Researcher → Scope → Drafter-A ‖ Drafter-B → Citation Tracer → Adjudicator → Critic) is functionally a 7-node graph — we just spell it out in Python rather than declaring it via a framework.

**When LangGraph is the right answer**: persistence across server restarts, human-in-the-loop pauses, conditional branching across dozens of steps. Past ~10 stages or any of these requirements, hand-rolling becomes false economy.

### Langfuse

**What it is**: self-hosted LLM observability stack. v3 (2026) ships as a 6-container Docker Compose (Postgres + ClickHouse + Redis + MinIO + worker + web).

**Why we didn't adopt it**: 6-container Compose stack is the wrong fit for a take-home that must run on a reviewer's laptop. Langfuse is excellent at scale — and in a multi-tenant production deploy we would absolutely run it.

**What we extracted**: the observability-as-a-design-primitive principle. Replaced with **Arize Phoenix** (SQLite-backed, embedded, OpenInference / OpenTelemetry standard). `phoenix.launch()` opens a local UI in seconds; the Studio Trace panel reads the same SQLite directly. Standards-based traces port to any future observability backend (Langfuse, Datadog, Honeycomb) without code changes.

### GPTCache

**What it is**: community-maintained semantic LLM cache. Last meaningful release pattern from ~2023.

**Why we didn't adopt it**: the abstraction is older-than-2024 thinking — separate server, separate config, separate failure modes. The 2026 SOTA is to either use provider-native prompt caching (Anthropic 90% / OpenAI 50%; Nemotron NIM doesn't ship native caching in May 2026) or do it in-process.

**What we built instead**: two layers, both prod-grade.
- **DiskCache** (Apache-2.0, SQLite-backed key-value, thread-safe) for exact match.
- **LanceDB `llm_cache` table** for semantic match. Same vector primitive that retrieves docs also caches LLM calls; cosine sim > 0.95 (configurable via `KLERK_SEMANTIC_CACHE_THRESHOLD`) is a hit.

**One primitive, two roles** is a clean architectural signal — we didn't add Redis / Upstash just to do caching.

### HippoRAG 2

**What it is**: Personalized PageRank over a phrase-passage knowledge graph; +2.6% F1 on multi-hop benchmarks vs vanilla dense retrieval.

**Why we didn't adopt it**: as of May 2026, HippoRAG 2 is alpha (`hipporag==2.0.0a4`), hardcoded to NV-Embed-v2, with no public LanceDB adapter. Forking + maintaining ~20-40h of plumbing for a +2.6% gain on a 25-doc corpus is a clear false economy. The +2.6% requires Wikipedia-scale KGs with high entity redundancy; on a corpus with ~4 seeded cross-doc facts the agent's multi-turn retrieval over hybrid+KG captures 95% of the benefit at 5% of the cost.

**What we extracted**: the *idea* of graph-walking retrieval as a tiebreaker. SHOULD-tier item #21 ships a NetworkX-based Personalized PageRank pass (`rag/pagerank.py`) that re-ranks ties in hybrid retrieval using entity centrality from our own KG. ~50 LOC, no framework dep, demonstrates the same conceptual move.

### LightRAG

**What it is**: dual-level retrieval (low entity-pair + high theme-cluster), pluggable backends.

**Why we didn't adopt it**: pluggable backends officially include PostgreSQL, MongoDB, Neo4j, Milvus, Qdrant, Redis, Faiss, Memgraph, OpenSearch — *not* LanceDB. A custom adapter is feasible but burns 8+ hours for marginal lift on a 25-doc corpus.

**What we extracted**: the dual-level concept. Our hybrid retrieval (BM25 sparse + dense vector via RRF) plus the BGE-Reranker pass plus the optional KG PageRank tiebreaker effectively gives us three retrieval signals fused — close enough in spirit to LightRAG's dual-level for this scale.

### Microsoft GraphRAG

**What it is**: LLM-built knowledge graph + community-detection clustering + hierarchical summarization.

**Why we didn't adopt it**: cost. Full GraphRAG construction over our 25-doc corpus would run $100+ (entity extraction → community detection → multiple LLM passes for hierarchical summaries). Our DIY JSON-mode extraction with Pydantic AI runs $10-50 for the same corpus and remains transparent.

**What we extracted**: the entity-and-relation-as-first-class-data principle. `agent/kg_extract.py` extracts entities with canonical ids + relations with `evidence_chunk` back-references — the contradict scan and the rubric's `citation_grounded` axis both rely on this lineage.

### Cognee

**What it is**: open-source (Apache-2.0, `topoteretes/cognee`) knowledge-engine for agents — multi-modal ingestion → knowledge structuring → access control & isolation → retrieval → memory → feedback → smarter agents. Production at Bayer, University of Wyoming. 1M+ pipelines/month.

**Cognee's pipeline maps almost 1:1 onto klerk**, minus enterprise concerns:

| Cognee primitive | klerk equivalent |
|---|---|
| Multi-modal ingestion | Docling + PyMuPDF (`klerk parse`, `klerk index build`) |
| Knowledge structuring | Pydantic AI → NetworkX (`klerk kg extract`) |
| Retrieval (semantic, graph, temporal) | LanceDB hybrid + BGE-Reranker + PageRank tiebreaker |
| Memory (short/long/procedural) | Phoenix traces + DiskCache + LanceDB `llm_cache` + APScheduler bg agent |
| Feedback loop (implicit / explicit) | Custom rubric + adjudicator + (STRETCH) drift detection |
| Self-improvement | STRETCH only |
| Access control & isolation | Not built (single-tenant; production concern) |

**Why we didn't adopt Cognee**: at klerk's scale (25-doc corpora, single-tenant), Cognee would replace our entire orchestration with a 10-15h framework learning curve, undercut the "own the loop" signal, and bring enterprise primitives (tenant isolation, ontology mapper, self-improvement loop) we don't need. **klerk is a deliberate slimmer-Cognee**: same primitives, hand-rolled, sized for the take-home. The Cognee MCP integration is STRETCH item #28 — at scale, swapping our APScheduler ingestion for `cognee` is a one-config-line change because the interface is already a standard MCP gateway.

### Other rejections (one-line)

- **Kùzu** — archived October 2025 (Apple acquisition). Don't build on it.
- **Memgraph** — BSL 1.1 license; non-commercial restriction wrong for a take-home demo.
- **Neo4j** — operationally heavy; needs a server, license review, JVM tuning. Wrong fit.
- **Cohere Embed v4 / Rerank 4** — best MTEB scores, but requires a Cohere API key. Wrong fit for a take-home where the reviewer might not have one. BGE-M3 + BGE-Reranker-v2-m3 self-hosted is the correct trade.
- **Cognee competitors** (Letta, mem0, Zep) — all framework-shaped memory layers. Same critique as Cognee at this scale.
- **CrewAI / AutoGen** — same orchestration-framework critique as LangGraph; less mature.
- **Trogon** (auto-TUI from Click) — unmaintained since 2025. We hand-built the Textual Studio TUI.
- **A full Ink rebuild of Pi's TUI** — Pi's diff-rendered custom TUI is 44k stars worth of polish we'd badly reinvent. We theme the shell instead.

## Hand-rolled primitives — and why

We intentionally implemented these ourselves rather than importing them:

| Primitive | Where | Why |
|---|---|---|
| Reciprocal Rank Fusion | `rag/fusion.py` (~30 LOC) | The formula is 1/(k+rank). Importing a library is overkill and obscures the math. |
| Recursive chunker | `rag/chunker.py` (~120 LOC) | Tokenizer-pluggable (tiktoken → transformers → char heuristic). Robust in restricted-network envs. |
| CRAG-lite loop | `agent/crag.py` (~150 LOC) | Anthropic stance — we own the decompose → retrieve → judge → correct → answer flow. |
| Adversarial proposal pipeline | `agent/proposal_pipeline.py` (~200 LOC) | The 7-stage flow with parallel A/B drafters + adjudicator is the headline 2026-paradigm extract. |
| 5-axis custom rubric | `eval/rubric.py` (~150 LOC) | The "differentiator beyond RAGAS." Deterministic, transparent, per-locale aggregatable. |
| Contradiction scan | `agent/contradiction.py` (~120 LOC) | Verb-stem bucketing + per-group LLM consistency check. The cheap signal beats a knowledge-graph-aware framework here. |
| Background ingestion | `agent/background.py` | APScheduler + asyncio, no Cognee/Letta/mem0 dep. |

## When to revisit these decisions

The whole table flips at:

- **>10k docs** → migrate the KG from NetworkX to a real graph DB (Neo4j or hosted), revisit Cognee
- **Multi-tenant** → Cognee or Letta become correct; SQLite cache won't carry
- **Production observability** → Langfuse self-hosted; Phoenix's embedded mode no longer fits
- **Multi-region serving** → LiteLLM Proxy mode (separate process), Portkey or Cloudflare AI Gateway in front
- **Strict cost SLAs** → Helicone or Portkey for routing + budget guardrails
- **Beyond simple multi-hop** → revisit HippoRAG 2 once it exits alpha and adds LanceDB support, or Path-RAG

The `docs/2026-landscape.md` doc captures the broader field so the migration paths above are concrete.
