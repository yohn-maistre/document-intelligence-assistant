# 2026 RAG / Agent Landscape — what klerk knows about and how it relates

> Companion to `design-decisions.md`. This doc maps the May 2026 landscape so
> the migration paths in the design-decisions doc are concrete.

## Anthropic's *Dynamic Workflows* — the paradigm klerk extracts

Anthropic launched [Dynamic Workflows in Claude Code](https://www.anthropic.com/research/claude-code) (May 2026, powered by Claude Opus 4.8). The headline shift: instead of orchestrating subagents through a static framework, **Claude writes a fresh orchestration script per task at runtime** and deploys parallel subagents that adversarially verify each other.

Four primitives, four levels of applicability for klerk:

| Primitive | klerk's application | Where it lives |
|---|---|---|
| **Multi-agent orchestration** | 7-stage proposal pipeline | `agent/proposal_pipeline.py` |
| **Adversarial self-verification** | Drafter-A ‖ Drafter-B → Adjudicator picks winner → Critic scores | `agent/proposal_pipeline.py` |
| **Runtime memory / context efficiency** | Pydantic AI structured tool outputs + Phoenix SQLite traces; intermediate state in structured store, not chat context | `agent/schemas.py`, `obs/phoenix.py` |
| **Long-running resumability** | SQLite checkpoint table — killed `klerk propose` resumes from last completed section | `agent/checkpoint.py` (SHOULD) |
| **LLM writes the orchestration script** | Too risky for a take-home (sandbox + code-exec safety). Documented as the natural evolution path. | STRETCH item #27 |

klerk's framing: **"klerk implements the spirit of Anthropic's May 2026 Dynamic Workflows paradigm — adversarial subagent verification, context efficiency via structured outputs, and SQLite-checkpointed resumability — without the runtime code-generation risk."**

## Agent observability — Phoenix vs Langfuse vs the rest

| Stack | Shape | Fit for take-home |
|---|---|---|
| **Arize Phoenix** | SQLite-backed, embedded, OpenInference/OTel | ✓ **klerk's pick** |
| OpenLLMetry (Traceloop) | OTel-native, file-based | Strong alternative; less polished UI than Phoenix |
| Langfuse | 6-container Compose stack | Production-grade; wrong for laptop demo |
| LangSmith | Managed cloud only | Locked to LangChain ecosystem |
| Helicone | Proxy-based, no SDK changes | Best for high-volume production traffic |
| Braintrust / Lunary | Managed eval + obs | OK but adds a hosted dep |

OpenInference is the OTel-for-LLMs spec that all of these are converging on. By using Phoenix + OpenInference, klerk's traces are portable to any of the above at migration time.

## Retrieval — what klerk knows about

| System | Status May 2026 | klerk's stance |
|---|---|---|
| **LanceDB hybrid (Tantivy BM25 + vector)** | Stable; native hybrid in March 2026 | ✓ Klerk's foundation |
| BGE-M3 + BGE-Reranker-v2-m3 | Stable; multilingual leader for Bahasa | ✓ Klerk's pick |
| Microsoft GraphRAG | Stable; $100+ per 25 docs | Skipped (cost). DIY Pydantic JSON-mode extraction. |
| LightRAG | EMNLP 2025; pluggable backends (no LanceDB) | Skipped (integration cost). Concept extracted via our reranker + PageRank tiebreaker. |
| HippoRAG 2 | Alpha (`2.0.0a4`); +2.6% F1 multi-hop | Skipped (alpha + LanceDB lock-in). Idea extracted in `rag/pagerank.py`. |
| RAPTOR | Stanford; hierarchical clustering | Best on >1k docs; overkill at 25. |
| R2R | Production-grade; Docker-served | Strong alternative if we needed managed multi-tenant. |
| RAGFlow | Multi-agent doc RAG with UI | Same shape but heavier; klerk is the take-home version. |
| Cohere Embed v4 / Rerank 4 | Best MTEB; API-key dep | Skipped — BGE self-hosted wins for take-home. |
| Voyage 3 / NV-Embed-2 | Strong embedding contenders | Future swap candidates. |

## Orchestration

| Framework | Status May 2026 | klerk's stance |
|---|---|---|
| **(none) — hand-rolled** | Per Anthropic stance | ✓ klerk's choice |
| LangGraph 2.0 | 90M monthly DLs; Uber/JPM/Klarna | The right answer at scale; signals scaffolding at take-home scale. |
| CrewAI | Strong prototyping ergonomics | Same critique. |
| AutoGen | Conversational multi-party | Niche fit. |
| Pydantic AI | Type-safe structured outputs | ✓ Klerk uses it as the structured-output primitive (not the full agent abstraction). |
| Mastra | TS-first, VC-backed | TS alternative to Pi if we ever ditch Pi. |
| Vercel AI SDK | Provider routing + stopWhen | Good SDK; not a TUI solution. |
| Flue (Astro Labs) | Headless CI/CD agent harness | Wrong shape for a chat agent. |

## Memory / knowledge engines

| System | Status | klerk's stance |
|---|---|---|
| **(hand-rolled background ingestion)** | ~80 LOC, APScheduler | ✓ Klerk's choice for the take-home |
| Cognee | Open-source (Apache 2.0), production at Bayer, 1M+ pipelines/mo | Klerk is a deliberate slimmer version. Cognee MCP is STRETCH item #28. |
| Letta (ex-MemGPT) | Production-ready Apr 2026 | Same critique as Cognee. |
| mem0 | Token-efficient memory; async tools | Same critique. |
| Zep | Temporal KG; LongMemEval leader | The right answer when temporal memory matters; overkill at our scale. |

## TUI / CLI stack

| Library | Stance |
|---|---|
| **Pi `@mariozechner/pi-coding-agent`** | Hidden runtime for klerk-cli chat; we get the diff-rendered TUI for free without rebuilding it. |
| Ink + chalk | klerk-cli's banner / help / version screens. |
| Textual | Studio TUI — 5 panels (corpus / eval / traces / proposals / KG). |
| textual-web | STRETCH — `textual serve` for browser deploy. |
| Hermes Agent (NousResearch) | The architectural pattern klerk copies (one tool layer, four surfaces, MCP-as-gateway). |
| Midday CLI | The product-feel reference (verbs as headline, agent-callable). |

## LLM gateways

| Gateway | Stance |
|---|---|
| **LiteLLM SDK (in-process)** | ✓ Klerk's pick — fallbacks + cost + cache hooks in one library, no extra process. |
| Portkey AI Gateway | Right answer for production multi-region + budget guardrails. |
| Helicone Gateway | Proxy + observability combined. |
| OpenRouter | Managed gateway; Nemotron support. |
| Vercel AI Gateway | Vercel-deployment-locked. |
| Cloudflare AI Gateway | Cloudflare Workers-locked. |

## Indonesian market context (May 2026)

- **SEA-HELM** is the canonical Bahasa benchmark (Singapore AI).
- **PDP Law** (enforced 2026) makes local inference a regulatory tailwind, not just a cost optimisation.
- klerk's `--locale id` mode routes to Qwen3 (current Bahasa-strong leader on SEA-HELM); the STRETCH local-LLM script downloads a Gemma 3 / Qwen 3.5 / Qwen 3.6 small model + sets up llama.cpp for a fully on-prem path.
- The 5-axis rubric reports per-locale, so Bahasa parity is visible in every eval run rather than buried.
