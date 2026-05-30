# 2026 landscape — what we explored, what we shipped

> One-page snapshot of the May 2026 RAG / agent landscape as it bore on
> klerk's design choices. The full reasoning per rejection (LangGraph,
> Langfuse, GPTCache, HippoRAG 2, LightRAG, Microsoft GraphRAG, Cognee,
> Letta, mem0, Zep, Kùzu, Memgraph, Neo4j, ColPali, ColQwen2.5, Jina-v4,
> omni-embed-nemotron-3b) lives in [`design-decisions.md`](design-decisions.md).
> This page is the lightweight map.

## Paradigm anchor

Anthropic's *Building Effective Agents* (Dec 2024, updated 2026) and the
*Dynamic Workflows* line in Claude Code (May 2026, Opus 4.8) set the
stance: prefer simple, composable patterns over frameworks; own the
loop; reach for graphs only when the state shape genuinely benefits.
klerk extracts the *spirit* (parallel adversarial subagents in the
proposal pipeline; structured tool outputs over chat-context state) but
doesn't take on runtime code-generation risk.

## What we picked

| Layer            | Pick                              | One-line rationale |
|------------------|-----------------------------------|--------------------|
| Chat LLM         | Nemotron via Cloudflare-tunneled LiteLLM proxy | Brief contract. No fallbacks. |
| Embedder         | BGE-M3 dense head (FlagEmbedding) | Multilingual, Bahasa-strong, self-hosted. |
| Reranker         | BGE-M3 ColBERT head (MaxSim)      | Same model file. ~1GB lighter than v4's separate cross-encoder. |
| Vector + BM25    | LanceDB embedded + Tantivy        | One process, one hybrid API call. |
| Fusion           | RRF (k=60), hand-rolled           | 30 LOC; no library obscures the formula. |
| Parser           | Docling + PyMuPDF fallback        | Layout-aware; PyMuPDF guard for torch install issues. |
| Orchestration    | Hand-rolled loops + LangGraph (1 flow) | Loop ownership = system ownership. LangGraph only for the Conflict Reporter. |
| Cache            | DiskCache (exact) + LanceDB semantic | Same vector primitive does retrieval + cache. |
| Observability    | Arize Phoenix (embedded SQLite)   | OpenInference standard; ports to Langfuse / Datadog later. |
| API surface      | FastAPI with SSE streaming        | Brief-mandated. 9 routes. |
| Studio UI        | Textual (TUI + browser via `textual serve`) | Five-panel keyboard-first; same source = TUI + browser. |
| Skill manifests  | agentskills.io v1                 | Portable across MCP-aware runtimes. |

## What we explored and rejected

| Candidate                       | Killed by |
|---------------------------------|-----------|
| LangGraph everywhere            | Over-applying a graph to single-loop flows signals the wrong instinct. We use it for one flow. |
| Langfuse self-hosted            | Six-container Compose stack; wrong fit for one reviewer's laptop. Phoenix embedded does the job. |
| GPTCache                        | Older-than-2024 server-shaped abstraction. DiskCache + LanceDB semantic in-process is cleaner. |
| HippoRAG 2                      | Alpha; hardcoded to NV-Embed-v2; no LanceDB adapter. +2.6% F1 doesn't justify 30+ hours of plumbing. |
| LightRAG                        | No LanceDB backend; custom adapter not worth the time. We approximate dual-level with hybrid+rerank+KG. |
| Microsoft GraphRAG              | $100+ to build a KG over 25 docs. Our Pydantic-AI JSON-mode extraction runs $10-50 and is transparent. |
| Cognee / Letta / mem0 / Zep     | Framework-shaped memory layers; right at scale, wrong at take-home size. |
| Kùzu                            | Archived Oct 2025 (Apple acquisition). |
| Memgraph                        | BSL 1.1 noncommercial clause wrong for the take-home. |
| Neo4j                           | Server, license review, JVM tuning. Wrong operational fit. |
| Cohere Embed v4 / Rerank 4      | Best MTEB; requires Cohere API key. Brief forbids paid embedders. |
| MinerU 2.5 parser               | 14% accuracy drop on non-Latin scripts (MDPBench Apr 2026). Risky for Bahasa. |
| ColPali / ColQwen2.5 / Jina-v4  | Bahasa+JP unbenchmarked; tables degrade to page blobs; CPU multi-vector 5-10× slower than text-native. |
| omni-embed-nemotron-3b          | NVIDIA OneWay Noncommercial license. |

## When to revisit any of the above

The table flips at:
- **>10k docs** → migrate KG to a real graph DB; revisit Cognee.
- **Multi-tenant** → Cognee / Letta become correct.
- **Strict cost SLAs** → Helicone / Portkey for budget routing.
- **Beyond simple multi-hop** → HippoRAG 2 once it exits alpha + adds LanceDB; or Path-RAG.
- **Page-image-heavy corpus** → re-evaluate the vision-language embedders once Bahasa/JP benchmark coverage lands.

For the per-rejection deep dive, see [design-decisions.md](design-decisions.md).
