# Project Handoff — klerk (Document Intelligence Assistant)

> **Internal handoff doc**. Captures full project state, brief alignment, locked decisions, and the next-session ordered work list. Push to the repo so any future Claude session (or human collaborator) can pick up cleanly without re-reading the entire conversation history. Not user-facing; will not be referenced in README. Keep this file gitignored from the public submission if needed.

---

## 1. At a glance

**Project**: PT Fata Organa Solusi — Middle AI Engineer take-home. Document Intelligence Assistant for an Indonesian-Japanese tech firm (CAC Holding Japan as named client). RAG over a 25-30 doc synthetic corpus ingested from Google Drive, served via FastAPI, using the provided Nemotron proxy as the only LLM.

**State**: ~60% brief-compliant. Strong on RAG primitives, Nemotron wiring, evaluation scaffolds, Textual Studio. **Missing the brief's pass/fail blockers**: FastAPI endpoints, Drive incremental sync, Docker, corpus, evaluation set, EVAL.md, DATA_GENERATION.md.

**Today**: 2026-05-29. **Deadline**: 2026-09-30 (4 months). **Brief estimate**: 8-10h focused work. **Brief hard gate**: 25h max. **Target**: 18-22h actual = MVP + curated differentiators.

**Branch**: `claude/agent-framework-planning-jJqQj` — clean working tree as of HEAD `bf8d2cb`. Merge to `main` only at submission time.

---

## 2. The brief (one-paragraph summary)

Build a production-ready Document Intelligence Assistant for a fictional Indonesian-Japanese tech firm: ingest from **Google Drive** (incremental: new/modified/deleted), RAG over **25–30 synthetic docs** (HR ≥8, SOPs ≥6, Minutes ≥6, FAQs ≥4, Org/Contact ≥2; ≥10 PDF, ≥10 DOCX; ≥3 Bahasa; ≥2 contradicting pairs; ≥2 with tables; ≥1 cross-doc reference), serve via **FastAPI** (`/chat`, `/ingest`, `/sync-status`, `/health`), use **only the provided Nemotron proxy** (no OpenAI/Anthropic/Cohere fallbacks — explicitly forbidden), implement **≥1 agentic capability** from menu A (Escalation Drafter) / B (Action Item Extractor) / C (Conflict Reporter), evaluate against an **own 20-Q set** (8 factual / 5 multi-hop / 3 conflict / 2 Bahasa / 2 trick — "system must say it doesn't know"), ship in **`docker compose up`**, document in **README + EVAL.md + DATA_GENERATION.md**. Submission: public GitHub repo + Drive folder ID shared `ydharmaw@fata-organa.com` (Editor) + self-assessment + hardware notes + connectivity confirmation.

Full brief in repo at `…` (uploaded only, not committed — see uploads dir `9d9af5bd-…/ef66ac9a-TakeHome_Technical_Assignment__Middle_AI_Engineer.pdf`).

---

## 3. LLM environment (Nemotron bundle — verified)

Bundle contents (decrypted from `nemotronpackage.zip`, password held by user — DO NOT commit the zip or `config.env`):

| File | Purpose |
|---|---|
| `config.env` | Credentials (LITELLM_KEY, CF_CLIENT_ID, CF_CLIENT_SECRET, PROXY_URL) |
| `nemotron_example.py` | OpenAI-SDK chat / streaming / reasoning examples |
| `test-nemotron.sh` | curl smoke test |

**Confirmed facts from the bundle README**:

- **Single model exposed**: `nemotron-3-nano-omni` — "Chat, streaming, step-by-step reasoning, complex questions". Likely an omni-modal Nemotron 3 Nano variant. We only use text input/output.
- **NO embedding endpoint** in the bundle → per brief Permitted clause, **must use a free local embedding model**.
- **NO reranking endpoint** in the bundle → if we want a reranker, it must be local.
- **Endpoint**: `https://llm-proxy.atlas-horizon.com/v1` (OpenAI-compatible).
- **Auth chain**: Cloudflare Access service token (CF-Access-Client-Id + CF-Access-Client-Secret headers) → LiteLLM virtual key (`Authorization: Bearer sk-…`).
- **Streaming**: supported via `stream=True`.
- **Concurrency**: not explicitly limited in the README; only mention of queuing is "curl timeout … retry in ~30s" under load. LiteLLM proxies default to concurrent-friendly. Multi-drafter (2-3 concurrent calls) is well within typical defaults. Fallback if rate-limited: sequential drafts.
- **Key validity**: 90 days from 2026-05-28 — expires **~2026-08-26**. Flag in submission email; document rotation steps in README.
- **Forbidden**: swapping `nemotron-3-nano-omni` for a different Nemotron variant. The pinned model IS the contract.

**Connection contract (used in repo's `src/klerk/llm/nemotron.py`, last commit `bf8d2cb`)**:

```python
client = OpenAI(
    api_key=os.environ["LITELLM_KEY"],
    base_url=f"{os.environ['PROXY_URL']}/v1",
    http_client=httpx.Client(headers={
        "CF-Access-Client-Id":     os.environ["CF_CLIENT_ID"],
        "CF-Access-Client-Secret": os.environ["CF_CLIENT_SECRET"],
    }),
)
response = client.chat.completions.create(
    model="nemotron-3-nano-omni", messages=[…], stream=True
)
```

`.env.example` should ONLY list these four vars + Drive vars. No `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / fallback flags.

---

## 4. Current implementation state

### Implemented (in repo)

| Path | Status | Notes |
|---|---|---|
| `src/klerk/llm/nemotron.py` | ✅ Wired | OpenAI client + CF headers per bundle contract |
| `src/klerk/llm/router.py` | ✅ Single-model | Routes everything to `nemotron-3-nano-omni`; no fallbacks |
| `src/klerk/llm/cache.py` | ✅ DiskCache | Exact-match cache (LanceDB semantic cache to be removed) |
| `src/klerk/rag/chunker.py` | ✅ | Token-aware chunking |
| `src/klerk/rag/embed.py` | ✅ BGE-M3 local | Multilingual (incl. Bahasa); CPU-only |
| `src/klerk/rag/store.py` | ✅ LanceDB | Embedded vector store + Tantivy BM25 |
| `src/klerk/rag/retrieve.py` | ✅ Hybrid | Vector + BM25 + RRF fusion |
| `src/klerk/rag/fusion.py` | ✅ | RRF implementation |
| `src/klerk/rag/rerank.py` | ⚠️ REFACTOR (v5) | Drop separate BGE-Reranker; call `bge_m3_model.encode(..., return_colbert_vecs=True)` and use ColBERT vectors for late-interaction MaxSim scoring |
| `src/klerk/rag/pagerank.py` | ⚠️ Over-eng | Tiebreaker; soft-demote to experimental |
| `src/klerk/agent/contradiction.py` | ✅ | Backbone for Conflict Reporter (Option C) |
| `src/klerk/agent/proposal_pipeline.py` | ✅ | Multi-drafter adversarial; will become Writer (Option D) |
| `src/klerk/agent/anomaly.py` | ⚠️ | Repurpose as Drift agent (Option E) |
| `src/klerk/agent/background.py` | ⚠️ APScheduler | Extract diff logic → `drive/sync.py`; rest → experimental |
| `src/klerk/agent/checkpoint.py` | ⚠️ Over-eng | Soft-demote to experimental |
| `src/klerk/agent/kg_extract.py` | ✅ Internal | Used by contradiction; no panel |
| `src/klerk/agent/kg_viz.py` | ⚠️ | Drop from MVP |
| `src/klerk/agent/crag.py` | ✅ | CRAG-lite re-query loop |
| `src/klerk/agent/faq.py` | ✅ | Corpus-learning bonus; CLI-only |
| `src/klerk/eval/rubric.py` | ✅ | 5-axis klerk rubric |
| `src/klerk/eval/ragas_runner.py` | ✅ | RAGAS baseline |
| `src/klerk/eval/golden.py` | ✅ | Golden YAML loader |
| `src/klerk/eval/seahelm_runner.py` | ⚠️ Over-eng | Soft-demote |
| `src/klerk/obs/phoenix.py` | ✅ | Embedded Phoenix observability |
| `src/klerk/studio/app.py` | ✅ | 5-panel Textual TUI (Corpus / Eval / Traces / Proposals / KG) — needs refactor: drop KG, rename Proposals→Outputs, add Chat as primary |
| `src/klerk/mcp/server.py` | ✅ | klerk-as-MCP server (quiet bonus) |
| `src/klerk/cli/` | ✅ | Typer verbs |
| `tests/` | ✅ 6 tests | chunker, eval_loader, fusion, imports, nemotron_config, schemas |
| `README.md` | ⚠️ | Needs full rewrite — brief-aligned, FastAPI-first, technical depth |
| `Makefile` | ✅ | Setup / demo / eval / studio verbs |
| `.env.example` | ⚠️ | Strip fallback vars |
| `pyproject.toml` | ⚠️ | Update description, drop apscheduler/watchdog from main, bump textual>=0.86 |

### Missing (brief pass/fail)

| Path | Status | Effort |
|---|---|---|
| `src/klerk/api/server.py` | ❌ Empty dir | ~450 LOC — FastAPI with 8 endpoints |
| `src/klerk/drive/sync.py` | ❌ Empty dir | ~280 LOC — Service Account + manifest diff + changes.list |
| `src/klerk/synth/gen.py` | ❌ Empty dir | ~200 LOC — Fata Organa corpus generator |
| `Dockerfile` | ❌ | ~30 lines (python:3.11-slim) |
| `docker-compose.yml` | ❌ | ~50 lines (api + phoenix; gws-mcp opt-in) |
| `evaluation_set.json` | ❌ | 20 Qs in brief's exact JSON schema |
| `EVAL.md` | ❌ | Methodology + per-Q table + aggregates + failures |
| `DATA_GENERATION.md` | ❌ | Corpus methodology + prompts + QC |
| `frontend/streamlit_app.py` | ❌ | ~30 LOC stub-with-comments |
| `data/synth/fata_organa/` | ❌ | 25-30 generated docs |

### Over-built / demote to `experimental/`

| Path | Why |
|---|---|
| `klerk-cli/` (TS shell) | Brief wants FastAPI primary; TS shell was the Pi-as-runtime play, out of scope |
| `pi-extension-klerk/` | "Pi contributor" angle irrelevant |
| `src/klerk/agent/checkpoint.py` | No long-running ops in MVP |
| `src/klerk/agent/background.py` (APScheduler timer) | Extract diff logic to `drive/sync.py`; rest demote (re-import APScheduler narrowly under `scheduled` extra for drift agent only) |
| `src/klerk/rag/pagerank.py` | Cross-encoder reranker is sufficient at k=8 |
| `src/klerk/eval/seahelm_runner.py` | Overkill for 2-Bahasa-Q eval |
| `src/klerk/agent/kg_viz.py` | KG panel dropped from Studio |
| LanceDB semantic cache wrapper | DiskCache exact-match is enough |

---

## 5. Locked decisions (research-informed, v5)

> **v5 nuances on v4** (2026-05-29 PM, post-research on multimodal embedders):
> 1. **Drop separate `BGE-Reranker-v2-m3`** — use BGE-M3's built-in ColBERT-style multi-vector head for late-interaction reranking. BGE-M3 has three output heads in one model (dense + sparse + ColBERT). Same vendor (BAAI), same weights file already loaded for embedding, ~1GB container reduction, one model load step instead of two, no quality regression on standard benchmarks. ~1h refactor to `src/klerk/rag/rerank.py`.
> 2. **Vision-frontier exploration recorded but not shipped** — evaluated ColPali / ColQwen2.5-3b-multilingual / Jina-embeddings-v4 / NVIDIA `omni-embed-nemotron-3b` as candidates to collapse parser + embed + rerank into ONE component (page-image-embed → omnimodal-LLM-consumes-page-images path). None ship because: (a) Bahasa Indonesia + Japanese **not benchmarked** on any multimodal embedder (ViDoRe v2 multilingual track silent on both), (b) tables degrade to page blobs hurting structured action-item extraction and table-grounded queries, (c) CPU multi-vector retrieval ~800ms-1s/page vs ~5-10ms text-native dense (5-10× regression), (d) `omni-embed-nemotron-3b` is NVIDIA OneWay **Noncommercial** license — disqualifies for a commercial take-home. Document full rationale + benchmark table in `docs/design-decisions.md` so reviewer sees "we evaluated the frontier and chose hybrid for these reasons" not "we picked BGE-M3 because it was already there".
>
> **v4 banner** (preserved): v4 corrects v3's incorrect assumption that the Nemotron bundle exposes embed + rerank endpoints. **The bundle exposes ONLY `nemotron-3-nano-omni` chat.** Per brief's Permitted clause, this mandates local embedding/reranking.

| Topic | Decision | Reasoning |
|---|---|---|
| **Chat LLM** | Single LiteLLM entry routing to `nemotron-3-nano-omni` via `proxy.atlas-horizon.com`. No fallbacks. | Brief forbids swapping; bundle pins this model |
| **Embedding** | Keep BGE-M3 local (multilingual incl. Bahasa, CPU-friendly, Apache-2.0 license) | Bundle has no embed endpoint → brief Permitted clause |
| **Reranker** | **No separate reranker model** (v5). Use BGE-M3's ColBERT (multi-vector late-interaction) head — same model file already loaded for dense + sparse embedding. MaxSim scoring at rerank time. | v5 refinement: BGE-M3 has 3 output heads (dense + sparse + ColBERT); ColBERT-mode rivals separate cross-encoder on standard benchmarks; saves ~1GB container weight + eliminates a second model load |
| **Container size** | ~1.5-2GB (torch + sentence-transformers + BGE-M3 only, no separate reranker model). No GPU assumed. | v5: reduced from ~2.5GB after dropping BGE-Reranker-v2-m3 in favor of BGE-M3 ColBERT head |
| **Vector store** | LanceDB embedded (already done; no separate DB container in compose) | Brief allows; embedded simplifies docker compose |
| **Parser** | Docling primary + PyMuPDF fallback. MinerU 2.5 NOT shipped (April 2026 MDPBench shows 14% accuracy drop on non-Latin scripts — risky for Bahasa) | Research finding; safety-first for Indonesian docs |
| **Hybrid retrieval** | Vector (LanceDB) + BM25 (Tantivy) + RRF fusion + cross-encoder rerank | Brief asks ≥1 improvement; we do hybrid + rerank (both top-shelf, both Should-Have) |
| **Drive integration** | Service Account (non-interactive, no OAuth consent during `docker compose up`) + manifest-based diff at `.klerk/drive-manifest.json` + Drive API `changes.list` with `pageToken` | Reviewer doesn't have to walk an OAuth flow |
| **Google Workspace CLI `gws`** | Opt-in only: optional compose service `gws-mcp` for advanced agentic Calendar/Gmail/Sheets reach. NOT on the `/ingest` path. | `gws` is pre-1.0; SDK is GA. Two integration points kept independent. |
| **Agentic capabilities** | All 5: A (Escalation), B (Action Items), C (Conflict — LangGraph spine), D (Writer — multi-drafter adversarial), E (Drift — scheduled). Brief asks ≥1; we ship 5. | User direction: push beyond brief on agentic surface |
| **Writer scope** | **Multi-drafter adversarial** (Drafter-A + Drafter-B + Adjudicator, ~400 LOC, ~5h). Verified safe against both docs: brief is silent on concurrent-request limits; bundle README documents no RPM/TPM cap, only "retry ~30s on timeout under load". LiteLLM proxies default to concurrent-friendly. Sequential fallback on 429. | User confirmed 2026-05-29 conditional on docs allowing concurrency — verified above |
| **LiteLLM hosting** | **In-process Python library** imported into FastAPI. No sidecar container. Already wired this way in `src/klerk/llm/`. | User confirmed 2026-05-29. Sidecar pattern reserved for if/when virtual-key per-team-budget becomes a real requirement. |
| **Drift agent execution** | **Both modes**: `GET /drift/recent` (on-demand, returns last N events from `.klerk/drift-events.jsonl`) + `POST /drift/scan` (manual trigger of a fresh scan, returns immediately with run_id) + scheduled nightly run via APScheduler at 02:00 UTC writing to the same JSONL. Manual endpoint always works regardless of scheduler state. | User confirmed 2026-05-29. |
| **LangGraph** | Spine for Conflict Reporter ONLY: 4-node `StateGraph` (retrieve_docs → pair_facts → judge_conflict → format_report). Single-loop Hermes-style for all other agents. | Signals "we know when graph vs loop"; minimal scope, ~150 LOC |
| **Pydantic AI** | Already in deps. Use for typed outputs at every agent boundary. | Free win; eliminates string-parsing brittleness |
| **agentskills.io spec** | Adopt for all 5 capabilities — one YAML manifest each in `src/klerk/agent/skills/`. Portable; importable by OpenJarvis/Hermes/OpenClaw users. | Ecosystem-aware signal; ~150 LOC total |
| **Execution modes** | Three (per OpenJarvis pattern): on-demand (A/B/C/D via HTTP), scheduled (E: drift detection nightly via APScheduler — re-imported narrowly under `[project.optional-dependencies] scheduled` extra), continuous (STRETCH — Drive `changes.watch` for live sync; flagged not blocking) | Pull APScheduler back from experimental for E only |
| **Studio frontend** | Promoted to primary frontend. Bloomberg-terminal feel. 5 panels: **Chat** (NEW, primary view, streaming + citations rail + status bar) / **Corpus** / **Eval** / **Traces** / **Outputs** (5 sub-tabs: Escalations / Action Items / Conflicts / Drafts / Drift). Browser deploy via `textual serve` (Textual >=0.86). | User direction: web-dev reviewer profile + visual distinction from typical Streamlit |
| **Streamlit stub** | `frontend/streamlit_app.py` — ~30 LOC, mostly comments. Documents what Streamlit shape would be + explains why we shipped Textual instead. Not wired. | User direction: leave a "obvious shape" footprint for reviewers expecting Streamlit |
| **MCP** | Keep `klerk-mcp` server as quiet bonus (one paragraph in `docs/architecture.md`). Plus `gws mcp` as opt-in agentic surface. | Multi-surface integration story without dominating README |
| **"I don't know"** | Formal path: when retrieval surfaces no chunks above threshold OR judge marks ungrounded, `/chat` returns `confidence: 0.0` + escalation_email + "I don't have enough info" answer. | Handles 2 brief trick Qs without hallucinating |
| **Latency reporting** | TTFT + total in every `/chat` response; aggregated p50/p99 in EVAL.md; live in Studio status bar | Brief Should-Have |
| **LLM-as-judge** | Implemented via the same `nemotron-3-nano-omni`. Bias disclosure in EVAL.md: judge = generator; absolute scores inflated, by-category deltas reliable. | Brief permits LLM-as-judge with disclosure |

### What we explicitly do NOT ship (and why)

- Pi runtime / TS shell (`klerk-cli/`) — out of brief scope; moves to `experimental/`
- Pi npm extension — out of scope; moves to `experimental/`
- Knowledge Graph UI panel — brief doesn't ask; KG stays internal for contradiction scanner
- SEA-HELM-style parity eval — overkill for 2-Bahasa-Q brief shape
- MinerU 2.5 — non-Latin script risk
- LanceDB semantic cache — DiskCache exact-match is enough
- PageRank tiebreaker — cross-encoder is sufficient
- **Vision-language embedders (ColPali / ColQwen2.5-multilingual / Jina-embeddings-v4)** (v5 explicit) — Bahasa/JP not benchmarked on multimodal embedders, tables degrade to page blobs, CPU multi-vector retrieval 5-10× slower than text-native hybrid. Full evaluation matrix in `docs/design-decisions.md`.
- **NVIDIA `omni-embed-nemotron-3b`** (v5 explicit) — NVIDIA OneWay Noncommercial license disqualifies for commercial take-home; mentioned as a notable also-ran in `docs/design-decisions.md` since it's the multimodal cousin of our chat model.
- **Separate cross-encoder reranker** (was BGE-Reranker-v2-m3 in v4) — BGE-M3's ColBERT head handles late-interaction reranking; one model file does both embed + rerank.
- Multi-tenancy / API auth / user accounts — brief Explicit Non-Requirements

---

## 6. Architecture (planned)

```
                          ┌────────────────────────┐
                          │  Reviewer's machine    │
                          │  docker compose up     │
                          └───────────┬────────────┘
                                      │
                ┌─────────────────────┼────────────────────────┐
                │                     │                        │
        ┌───────▼────────┐   ┌────────▼─────────┐   ┌──────────▼─────────┐
        │   api          │   │   phoenix        │   │   gws-mcp (opt-in) │
        │   FastAPI:8000 │   │   :6006          │   │   stdio/http       │
        └────┬───────────┘   └──────────────────┘   └────────────────────┘
             │
   ┌─────────┼─────────────────────────────────────────────┐
   │         │ /chat /ingest /sync-status /health          │
   │         │ /actions /conflicts /draft /drift           │
   │         ▼                                             │
   │   ┌─────────────┐    ┌─────────────┐    ┌────────────┐│
   │   │ drive/sync  │    │ rag/        │    │ agent/     ││
   │   │ Service Acc │───▶│ chunker     │───▶│ A B C D E  ││
   │   │ + manifest  │    │ embed BGE-M3│    │            ││
   │   │ + changes   │    │ store Lance │    │ C: LangGr. ││
   │   └─────────────┘    │ retrieve    │    │ orchestrate││
   │                      │ rerank M3-CB│    └─────┬──────┘│
   │                      └──────┬──────┘          │       │
   │                             │                 │       │
   │                             └────────┬────────┘       │
   │                                      ▼                │
   │                       ┌──────────────────────────┐    │
   │                       │ llm/ → LiteLLM           │    │
   │                       │ → CF Access              │    │
   │                       │ → Nemotron proxy         │    │
   │                       │ → nemotron-3-nano-omni   │    │
   │                       └──────────────────────────┘    │
   └───────────────────────────────────────────────────────┘
```

LangGraph state graph (Conflict Reporter, Option C):

```
retrieve_docs ──▶ pair_facts ──▶ judge_conflict ──▶ format_report
   (top-k)        (cross-doc       (per-pair          (structured
                  candidates)      LLM call)          report w/
                                                       timestamps)
```

---

## 7. Next steps (ordered, ~18h)

1. **Demote + cleanup pass + reranker refactor** (~1.5h, +0.5h for v5 rerank refactor)
   - `git mv klerk-cli/ experimental/ts-shell/`
   - `git mv pi-extension-klerk/ experimental/pi-extension/`
   - `git mv src/klerk/agent/checkpoint.py experimental/`
   - `git mv src/klerk/rag/pagerank.py experimental/`
   - `git mv src/klerk/eval/seahelm_runner.py experimental/`
   - Extract diff/manifest logic from `agent/background.py` → `drive/sync.py`; move rest to experimental
   - Write `experimental/README.md` (per-item rationale)
   - Strip fallback vars from `.env.example` (keep only LITELLM_KEY, CF_CLIENT_ID, CF_CLIENT_SECRET, PROXY_URL, GOOGLE_APPLICATION_CREDENTIALS, DRIVE_FOLDER_ID)
   - `pyproject.toml`: drop apscheduler/watchdog from main; re-add under `[project.optional-dependencies] scheduled` extra; bump `textual>=0.86`; add `langgraph>=0.2.0`; update description
   - **(v5) Refactor `src/klerk/rag/rerank.py`**: drop the separate `BAAI/bge-reranker-v2-m3` SentenceTransformer load entirely. Instead, call the already-loaded BGE-M3 model with `model.encode(texts, return_colbert_vecs=True, return_dense=False, return_sparse=False)` at index time to cache token-level vectors alongside chunks. At rerank time, compute MaxSim(query_colbert_vecs, doc_colbert_vecs) for the top-k retrieved chunks and re-sort. Remove `bge-reranker-v2-m3` from `pyproject.toml` extras + any pre-fetch / Docker pre-bake scripts. Update `tests/test_imports.py` and add `tests/test_rerank_colbert.py` (sanity: identical query > paraphrase > unrelated).

2. **FastAPI server** (~4h)
   - `src/klerk/api/server.py`: 8 endpoints
   - `POST /chat` (SSE), `POST /ingest` (BackgroundTask, returns 202), `GET /sync-status`, `GET /health`
   - `POST /actions/extract` (B), `POST /conflicts/scan` (C), `POST /draft` (D), `GET /drift/recent` + `POST /drift/scan` (E)
   - Pydantic validation; FastAPI exception handlers; latency middleware (TTFT + total)
   - Test: `tests/test_api_endpoints.py`

3. **Drive incremental sync** (~3h)
   - `src/klerk/drive/sync.py`: Service Account auth, list folder, manifest at `.klerk/drive-manifest.json`, incremental diff
   - Wraps `changes.list` with stored `pageToken`
   - Test: `tests/test_drive_sync.py` (manifest diff correctness with mocked Drive responses)

4. **Docker** (~1h)
   - `Dockerfile`: python:3.11-slim, multi-stage (build → runtime); pre-download BGE-M3 weights (~1.2GB; single model — no separate reranker per v5) so cold-start doesn't fetch on first run
   - `docker-compose.yml`: services `api` (FastAPI + LanceDB embedded) + `phoenix` (:6006); optional commented `gws-mcp` service
   - Verify `docker compose up` from clean checkout end-to-end

5. **Corpus generation** (~3h)
   - `src/klerk/synth/gen.py`: Fata Organa-Japanese spec
   - Categories: HR ≥8 / SOPs ≥6 / Minutes ≥6 / FAQs ≥4 / Org ≥2
   - Formats: ≥10 PDF (reportlab), ≥10 DOCX (python-docx), rest MD/TXT
   - Mandatory: ≥3 Bahasa, ≥2 contradicting pairs (date-stamped 2023 vs 2025), ≥2 with structured tables, ≥1 explicit cross-doc reference
   - Japanese cultural sprinkle (CAC Holding mentions, Tokyo addresses, JST timestamps, mixed names) — no JP-language processing required
   - Output to `data/synth/fata_organa/`
   - Cache Nemotron responses in `data/synth/.cache/` for free regen

6. **Evaluation set + EVAL.md scaffold** (~2h)
   - `evaluation_set.json` at repo root: 20 Qs in brief's exact JSON schema
   - 8 factual / 5 multi-hop / 3 conflict / 2 Bahasa / 2 trick
   - Rewire `src/klerk/eval/golden.py` to read brief's schema
   - Initial `EVAL.md` skeleton (filled in after step 11)

7. **Agentic capabilities A + B + D + E** (~3h)
   - `src/klerk/agent/escalation.py` (A) — ~100 LOC; structured `{to, cc, subject, body}`; triggers inline within `/chat` on low confidence
   - `src/klerk/agent/action_items.py` (B) — ~80 LOC; structured action-item JSON; `/actions/extract` endpoint
   - `src/klerk/agent/writer.py` (D) — adapt `proposal_pipeline.py`; multi-drafter adversarial (Drafter-A + Drafter-B + Adjudicator); ~400 LOC; `/draft` endpoint; concurrent calls to nemotron-3-nano-omni
   - `src/klerk/agent/drift.py` (E) — adapt `anomaly.py`; corpus-version diff; scheduled nightly via APScheduler at `src/klerk/scheduled/drift_runner.py`; `/drift/recent` endpoint
   - `src/klerk/agent/_models.py` — Pydantic models for all 5 outputs
   - Test: `tests/test_agentic.py`

8. **LangGraph Conflict spine + skill manifests** (~2h)
   - `src/klerk/orchestrate/conflict_graph.py` — 4-node StateGraph (retrieve_docs → pair_facts → judge_conflict → format_report)
   - Checkpoint to `.klerk/langgraph-state.db` (SQLite); supports `/conflicts/scan?resume=true`
   - `src/klerk/agent/skills/{escalation,action_items,conflict_report,writer,drift}.yaml` — agentskills.io manifests
   - README has the StateGraph mermaid diagram
   - Test: `tests/test_conflict_graph.py`

9. **Studio refactor** (~2h)
   - Drop KG panel; rename Proposals → Outputs (sub-tabs: Escalations / Action Items / Conflicts / Drafts / Drift)
   - Add Chat panel as primary view: streaming answer + citations rail + status bar (model + cache hit + TTFT + total)
   - Verify `textual serve src/klerk/studio/app.py` browser-deploy works
   - Bloomberg-terminal aesthetic preserved

10. **Streamlit stub + DATA_GENERATION.md + Workspace CLI integration doc** (~1h)
    - `frontend/streamlit_app.py` — comment-only skeleton
    - `DATA_GENERATION.md` — corpus methodology, prompts, QC
    - `docs/integrations/gws-mcp.md` — opt-in Workspace CLI MCP wiring

11. **Run 20-Q eval; finalize EVAL.md; README rewrite** (~2h)
    - `klerk eval run` → per-Q table + aggregates
    - LLM-as-judge with bias disclosure
    - Aggregate: overall, by-category, by-locale, TTFT/total p50/p99
    - Honest failure analysis
    - README full rewrite: brief-aligned, FastAPI-first, technical depth, ASCII arch diagram + LangGraph mermaid, design decisions (incl. why local BGE-M3 with ColBERT-head reranking, why NOT ColPali / ColQwen2.5-multilingual / Jina-v4 / omni-embed-nemotron-3b), OpenJarvis/Hermes/OpenClaw design-influences credit, agentskills.io section, Workspace CLI advanced section, limitations, hardware notes
    - **Write `docs/design-decisions.md` vision-frontier section** (v5 nuance 2): benchmark matrix comparing ColPali / ColQwen2.5-multilingual / Jina-v4 / omni-embed-nemotron-3b / BGE-M3 with columns: params, multilingual (Bahasa? JP?), table-structure preservation, CPU latency per page, license, container delta. Conclusion paragraph: chose BGE-M3 hybrid with ColBERT-head reranking; revisit if corpus becomes figure-heavy or multimodal embedders gain Bahasa/JP benchmark coverage.
    - Strip docs/2026-landscape.md → one short "explorations" section

12. **Final smoke + commit + merge to main** (~30 min)
    - `make demo` + `make eval` + `docker compose up` smoke
    - `pytest tests/` — all pass
    - Merge `claude/agent-framework-planning-jJqQj` → `main`
    - Tag

13. **Submission** (~15 min)
    - Public repo URL
    - Drive folder ID shared with `ydharmaw@fata-organa.com` (Editor)
    - 1-paragraph self-assessment (strongest: …, weakest: …)
    - Hardware notes
    - "Connected to Nemotron proxy at https://llm-proxy.atlas-horizon.com successfully on YYYY-MM-DD"
    - Flag CF token expiry date (~2026-08-26)

---

## 8. Critical files & locations

```
document-intelligence-assistant/
├── HANDOFF.md                         # this file
├── README.md                          # to rewrite (step 11)
├── EVAL.md                            # to create (step 11)
├── DATA_GENERATION.md                 # to create (step 10)
├── evaluation_set.json                # to create (step 6)
├── pyproject.toml                     # to update (step 1)
├── Dockerfile                         # to create (step 4)
├── docker-compose.yml                 # to create (step 4)
├── .env.example                       # to clean (step 1)
├── Makefile                           # keep, extend
├── frontend/
│   └── streamlit_app.py               # stub (step 10)
├── data/
│   └── synth/fata_organa/             # to generate (step 5)
├── src/klerk/
│   ├── api/server.py                  # to create (step 2) — 8 endpoints
│   ├── drive/sync.py                  # to create (step 3) — manifest diff
│   ├── synth/gen.py                   # to create (step 5) — corpus gen
│   ├── orchestrate/conflict_graph.py  # to create (step 8) — LangGraph
│   ├── integrations/gws_mcp.py        # to create (step 10) — opt-in MCP
│   ├── scheduled/drift_runner.py      # to create (step 7) — APScheduler
│   ├── agent/
│   │   ├── _models.py                 # to create (step 7) — Pydantic
│   │   ├── escalation.py              # to create (step 7) — A
│   │   ├── action_items.py            # to create (step 7) — B
│   │   ├── writer.py                  # to create (step 7) — D, adapt proposal_pipeline.py
│   │   ├── drift.py                   # to create (step 7) — E, adapt anomaly.py
│   │   └── skills/*.yaml              # to create (step 8) — agentskills.io
│   ├── studio/app.py                  # to refactor (step 9) — Chat as primary, drop KG
│   ├── rag/                           # keep as-is
│   ├── llm/                           # keep as-is (already wired to bundle)
│   ├── eval/                          # rewire golden.py (step 6)
│   └── mcp/server.py                  # keep (quiet bonus)
├── experimental/                      # to populate (step 1)
└── tests/
    ├── test_api_endpoints.py          # to create (step 2)
    ├── test_drive_sync.py             # to create (step 3)
    ├── test_agentic.py                # to create (step 7)
    └── test_conflict_graph.py         # to create (step 8)
```

---

## 9. Risks & known issues

| Risk | Severity | Mitigation |
|---|---|---|
| Bundle README doesn't doc concurrent-request limits | Medium | Multi-drafter writer = 2-3 concurrent calls; well below typical LiteLLM defaults. Fallback: sequential drafts on 429. |
| BGE-M3 weights cold-fetch ~1.2GB on first container run (v5: single model, no separate reranker) | Medium | Pre-bake into Docker image via multi-stage build; document image size in README |
| CF Access service token expires ~2026-08-26 (90-day key, issued 2026-05-28) | High at expiry | Document rotation steps in README; flag in submission email |
| All-local embedding (BGE-M3 with ColBERT-head reranking, no separate reranker) = ~1.5-2GB container | Low (necessary) | Brief mandates local; v5 reduced size by ~1GB vs v4 by collapsing reranker into BGE-M3 |
| MinerU 2.5 omitted despite SOTA layout | Low | 14% non-Latin script accuracy drop (MDPBench Apr 2026) is too risky for Bahasa docs; Docling is safer |
| First-time Drive sync latency (60-90s for 25-30 docs) | Medium | FastAPI BackgroundTasks; `/ingest` returns 202; clients poll `/sync-status` |
| LLM-judge bias (judge = generator model) | Medium | Disclose in EVAL.md; use retrieval recall@k as secondary metric grounded outside LLM |
| Nemotron-3-nano-omni reasoning quality on Bahasa | Unknown | 2 Bahasa Qs in eval; honestly report if accuracy trails English |
| LangGraph adds ~15MB + ~150 LOC | Low | Worth the demo signal; isolated to one flow |
| Workspace CLI `gws` pre-1.0 stability | Low (opt-in) | Default-off in docker-compose; SDK handles `/ingest` |
| Phoenix observability SQLite file grows | Low | Add log rotation in README "Operations" section if eval runs are heavy |

---

## 10. Setup for next session (commands to run on resume)

```bash
# 1. Confirm branch
git checkout claude/agent-framework-planning-jJqQj
git pull --ff-only origin claude/agent-framework-planning-jJqQj

# 2. Confirm env
ls .env  # should NOT exist (gitignored); copy from .env.example
cp .env.example .env  # then paste values from /tmp/nemotron-package/nemotron-user-package/config.env

# 3. Sync deps
uv sync

# 4. Smoke test Nemotron proxy
bash /tmp/nemotron-package/nemotron-user-package/test-nemotron.sh

# 5. Resume work — start at step 1 in section 7 of this file
```

**Bundle location** (decrypted, in this session's tmp): `/tmp/nemotron-package/nemotron-user-package/`. Password held by user (was: `F4t4Org4n4!`). Re-extract from `~/.claude/uploads/6b70b1bf-…/81bc8bc6-nemotronpackage.zip` if needed in a new session.

**Brief location** (uploaded only): `~/.claude/uploads/9d9af5bd-…/ef66ac9a-TakeHome_Technical_Assignment__Middle_AI_Engineer.pdf`.

**OpenJarvis README** (design influence reference): `~/.claude/uploads/7d7eb16b-…/681e4dd4-READMEopenjarvis.md` or duplicate at `~/.claude/uploads/9419e92f-…/`.

---

## 11. Side answers (recurring questions)

- **Unverified commits**: skip fixing. No merge impact; reviewer sees `main` post-merge, not signature badges.
- **Branch rename**: skip. Harness pins to `claude/agent-framework-planning-jJqQj`; reviewer sees `main` after submission merge.
- **README framing**: fully technical depth — no "team profile" or "review audience" language bleeds out from this internal handoff into public docs.
- **Brief's "8-10h" estimate**: floor, not ceiling. The hard gate is 25h. We target ~18-22h actual.
- **Brief's "deduct points for over-engineering"**: leaked from Mas Yanistra's chat per user. Spirit: *don't ship half-built mansions*, not *don't be ambitious*. Push on agentic surface; stay tight on infrastructure.

---

## 12. v6 plan — agentic orchestrator + Stack C lock-in (2026-05-30)

v5 shipped (steps 1-11). Branch `claude/agent-framework-planning-jJqQj`
at `29fc6b8`. Working tree clean. 143 tests green. v6 is additive on top.

### 12.1 Mission

Promote `/chat` from a single-shot RAG endpoint to a multi-turn LangGraph
orchestrator that routes among six tools. Surface the agent's reasoning
in a Live Chat panel + Activity panel inside Studio. Ship a constrained-env
demo path (remote embeddings + browser-served lite TUI). Promote Pi from
`experimental/` as a second polished CLI surface.

### 12.2 Stack decision — locked

**Stack C**: Python-only orchestrator (LangGraph + PydanticAI) for the
FastAPI submission path; Pi 0.78+ promoted from `experimental/` as a
second CLI surface (`klerk-cli` on npm) for developers who prefer
terminal-native chat.

**Three stacks considered**:

| Stack | Orchestrator | Cost | Verdict |
|---|---|---|---|
| A | Pi (Node sidecar) + LangGraph for sub-pipelines | Node runtime in Docker; JSONL bridge; 4-process hop per tool call; ~12h | Rejected — Node tax on the primary path |
| B | LangGraph in Python only | ~6h; Python-end-to-end | Rejected on its own — Pi work already exists, throwing it away wastes the investment |
| **C** | **LangGraph in Python + Pi as 2nd CLI surface** | **~22h; two surfaces, both native to their env** | **Locked** |

**Pi research summary** — confirmed via SDK inspection:
`createAgentSession()`, built-in compaction + multi-session JSONL +
branching/forking + 25+ provider support; ships in 4 modes (TUI /
print-JSON / RPC / SDK). Explicitly rejects MCP per Mario's "No MCP"
design stance ([blog](https://mariozechner.at/posts/2025-11-02-what-if-you-dont-need-mcp/)).
The `@mariozechner/pi-coding-agent` package rebranded to
`@earendil-works/*` (maintained by Mario Zechner + Armin Ronacher);
we migrate to the new org as part of the promotion.

Full rationale + the list of rejected alternatives (Stack A, MinerU,
semantic cache, etc.) lives in `.planning/v6-plan.md` "Decision log".

### 12.3 Architecture target

```
                         ┌─────────────────────────────────────┐
                         │  LangGraph Chat Orchestrator        │
   Studio TUI            │  create_react_agent + state graph   │
   (Textual, Python)─────│  sliding-window compaction          │
   HTTP/SSE              │  6 tools dispatched as graph nodes  │
                         └────────┬────────────────────────────┘
                                  │
       ┌──────────────────────────┼─────────────────────────────┐
       ▼                          ▼                             ▼
  search_hybrid             draft_doc                    scan_conflicts
  (LiteLLM + LanceDB)       (LangGraph sub-graph,        (LangGraph,
                             7-stage adversarial)         existing, 4-node)
       ▼                          ▼                             ▼
  extract_actions           ingest_path                   sync_drive
  (PydanticAI)              (ingest_runner)               (drive/sync.py)

  Background  ─── drift_runner (APScheduler, separate process)

                            ─── ─── ─── ───

  Second CLI surface (promoted from experimental/):

  klerk-cli (npm, TS)
  ──────────────────
  Pi 0.78+ SDK ─── pi-extension-klerk (native TS tools, NO MCP)
                              │
                              ▼
                  HTTP → FastAPI internal tool endpoints
                  (same Python functions the orchestrator routes)
```

**SSE event stream** (downward-compatible with v5; new types are
`tool_call`, `tool_result`, `session`):

```
data: {"event": "session",     "session_id": "..."}        # NEW first frame
data: {"event": "tool_call",   "name": "search_hybrid", "args": {...}}
data: {"event": "tool_result", "name": "search_hybrid", "summary": "12 chunks"}
data: {"event": "token",       "text": "..."}              # unchanged
data: {"event": "citations",   "citations": [...]}         # unchanged
data: {"event": "done",        "ttft_ms": ..., ...}        # unchanged
```

### 12.4 Locked scoping decisions

1. **LangGraph orchestrator** — `create_react_agent`; MAX_TOOL_HOPS=4.
2. **Multi-turn memory** — server-side `SessionStore` (JSONL per session)
   + sliding-window compaction (last 3 turns verbatim; older summarised
   to ≤200 tokens via Nemotron). Token budget 16K.
3. **doc_writer rename** — `proposal_pipeline.py` → `doc_writer.py`;
   CLI verb `klerk propose` → `klerk write`; skill manifest + MCP tool
   name + README all updated.
4. **doc_writer as LangGraph sub-graph** — 7 stages become explicit
   nodes; checkpoints under `.klerk/checkpoints.db`.
5. **PydanticAI migration** — `action_items.py`, `kg_extract.py`, and
   `contradiction.judge_pair()` migrate from raw-LiteLLM JSON-schema to
   `Agent(result_type=PydanticModel)`. Closes the v5 docs/reality gap
   (pydantic-ai was in deps but `grep "pydantic_ai"` returned 0 hits).
6. **Pi as 2nd surface** — `experimental/ts-shell/` graduates to
   top-level `cli/`; `pi-extension-klerk` rewritten on Pi's native
   `defineTool()` typebox API (no MCP); both packages migrate to
   `@earendil-works/*` latest.
7. **Lite TUI right rail = five widgets**: SessionPanel, CorpusStat,
   Activity (tool calls), RecentTraces (chat exchanges), EvalHeader.
8. **Drive upload includes `--dry-run`**.
9. **Remote embed backend** = provider-neutral via env-var
   (`KLERK_EMBED_REMOTE_URL` + `KLERK_EMBED_REMOTE_KEY` +
   `KLERK_EMBED_REMOTE_MODEL`); `.env.example` lists DeepInfra / Jina /
   OpenRouter as known-compatible.
10. **No remote reranker** — remote mode = RRF-only; ColBERT MaxSim
    raises `RuntimeError`; rerank module catches + falls back to RRF.

### 12.5 Implementation order (~22h, 8 clusters)

| # | Cluster | Time |
|---|---|---|
| 1 | Backend foundations: remote embed + rerank fallback + Drive upload (`--dry-run`) | ~3h |
| 2 | doc_writer rename + LangGraph sub-graph refactor | ~2h |
| 3 | PydanticAI migration: action_items, kg_extract, contradiction.judge_pair | ~1.5h |
| 4 | Multi-turn chat: SessionStore + sliding-window + LangGraph orchestrator + 6 tools + `/chat` rewire | ~5h |
| 5 | Studio TUI: LiveChatPanel + ActivityBlock + SessionPanel + Lite layout + `--serve` unstub | ~4h |
| 6 | Pi 2nd surface: pi-extension on native tools + `@earendil-works/*` migration + `experimental/ts-shell/` → `cli/` promotion + publish prep (don't publish yet) | ~3h |
| 7 | Demo + docs: `make demo-lite` + README sweep + `DATA_GENERATION.md` §10 + `.env.example` | ~2.5h |
| 8 | Commits (6 atomic) + merge to main | ~30min |

### 12.6 File touch summary

20 source files, 5 new test files. Net add ~1900 LOC; ~370 LOC new tests.

New: `src/klerk/api/session.py`, `src/klerk/agent/orchestrator.py`,
`src/klerk/agent/tools.py`, `src/klerk/agent/doc_writer_graph.py`,
`src/klerk/studio/widgets/{live_chat,activity,sessions}.py`,
`tests/test_{embed_remote,session_store,orchestrator}.py`.

Renamed: `proposal_pipeline.py` → `doc_writer.py` (+ test file + skill
YAML + CLI verb + MCP tool name).

Moved: `experimental/ts-shell/` → `cli/` (top-level).

Substantially modified: `src/klerk/rag/{embed,rerank}.py`,
`src/klerk/drive/sync.py`, `src/klerk/cli/{main,drive_cmd}.py`,
`src/klerk/api/{server,models}.py`, `src/klerk/studio/app.py`,
`src/klerk/agent/{action_items,kg_extract,contradiction,prompts/system}.py`,
`experimental/pi-extension/src/`.

### 12.7 Explicitly out of scope (v7+)

- PydanticAI for the orchestrator (staying LangGraph in v6).
- Pi as the primary orchestrator (Stack A) — Node sidecar tax.
- Remote ColBERT-aware rerank (Jina multi-vector + local MaxSim).
- Quantised BGE-M3 (INT8 ONNX) as a third backend tier.
- Drift as a routable tool (it's a background loop).
- Self-hosted Modal / Vespa templates.
- OAuth alternative to Drive Service Account.
- `/conflicts/scan?resume=run_id` resumption surface.
- Publishing `klerk-cli` to npm (publish-ready locally; defer to
  post-submission).

### 12.8 Risks specific to v6

| Risk | Likelihood | Mitigation |
|---|---|---|
| Nemotron tool-routing unreliable (LangGraph picks wrong tool) | Medium | Pre-seed `search_hybrid` every turn; explicit tool-selection prompt; fallback path keeps system useful |
| LangGraph + LiteLLM tool-call shape mismatch | Low-Medium | LangGraph 0.2+ supports OpenAI-format tool calls; LiteLLM translates Nemotron tool-call format |
| Pi 0.73 → 0.78 + `@earendil-works/*` rebrand API drift | Medium | Verify `dist/index.d.ts` matches integration; pin exact 0.78.x; rebrand still in flight |
| PydanticAI ⇄ Nemotron-via-OpenAI-proxy edge cases | Low | `OpenAIModel` accepts custom `base_url` + `http_client` headers; standard pattern |
| LiveChatPanel SSE backpressure under slow Nemotron | Low | Textual reactive widgets handle async; no event-loop blocking |
| Drive upload targets wrong folder | Low (mitigated) | `--dry-run` printed first; `--to` mandatory; `drive.file` scope limits blast radius |
| Sliding-window summary cost (extra Nemotron call per overflow) | Low | Cached by `(session_id, last_summarised_turn)`; summary ≤200 tokens |

### 12.9 Resume commands for next session

```bash
git checkout claude/agent-framework-planning-jJqQj
git pull --ff-only origin claude/agent-framework-planning-jJqQj
uv sync                              # Python deps
pnpm install                         # TS deps for cli/ + experimental/pi-extension/
cp .env.example .env                 # if not already done
# verify Nemotron proxy still healthy
bash /tmp/nemotron-package/nemotron-user-package/test-nemotron.sh
# verify Pi rebrand pinned correctly
pnpm ls --depth 0 | grep earendil
# start at cluster 1, step 1.1 (remote embed backend)
```

The full work breakdown + decision log + changelog lives in
`.planning/v6-plan.md` (committed alongside this handoff).

---

*End of handoff. If you're a new session starting here: read sections 1-3 first, then 12 (v6 plan). Sections 4-6 are deep context. Sections 7-11 are v5 reference. Section 12 is the active workplan.*
