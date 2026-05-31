# klerk

> **Chat with your company's documents — privately.** klerk is a self-hosted
> document-intelligence agent that ingests your files from Google Drive, answers
> questions with grounded citations, and runs entirely against *your own* LLM —
> no third-party AI APIs, no data leaving your perimeter.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)
![Docker](https://img.shields.io/badge/run-docker%20compose-2496ED)
![Tests](https://img.shields.io/badge/tests-247%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-black)

klerk pairs hybrid retrieval (dense + lexical + reranking) with an agentic chat
loop that knows when to search, when to cross-check sources, and when to say
*"I don't know"* rather than guess. It speaks **English and Bahasa Indonesia**,
ships two polished surfaces — a **FastAPI service** and a **terminal/browser
cockpit** — and exposes every capability as an agent-friendly CLI so it slots
into cron jobs, scripts, and other agents as cleanly as it serves humans.

---

## Features

- **Grounded RAG chat** — hybrid retrieval (vector + BM25 + RRF + ColBERT
  rerank) with inline source citations and honest *"not in the corpus"*
  handling instead of hallucination.
- **Agentic, not fixed-workflow** — a ReAct-style loop routes among in-process
  tools (search, conflict-scan, action-item extraction, drafting, Drive sync)
  and streams its reasoning as it goes.
- **Google Drive ingestion** — incremental sync detects new / modified / deleted
  files; handles PDF, DOCX, Markdown, and plain text.
- **Self-hosted LLM only** — all generation routes through a single configurable
  gateway (no OpenAI / Anthropic / Cohere). Your documents never leave your
  network.
- **Multilingual** — BGE-M3 embeddings + a multilingual model give first-class
  Bahasa Indonesia support alongside English.
- **Long-term memory** — a persistent identity + recalled-facts layer so the
  agent carries context across sessions.
- **Two surfaces, one engine** — a FastAPI backend (`:8000`) and a
  Bloomberg-style Textual dashboard, usable in the terminal *or* served to the
  browser (`:8001`) with no separate frontend build.
- **Agent-friendly CLI** — every verb supports `--agent/--json` for clean,
  machine-parseable output (the external tool contract for scripts, cron, and
  other agents).
- **Built-in sample-corpus generator** — spin up a realistic set of company
  documents (HR policies, SOPs, meeting minutes, FAQs) for demos and testing
  before you connect real data.
- **Observability + evaluation** — OpenTelemetry traces via Arize Phoenix, and a
  repeatable eval harness (custom rubric + RAGAS) over a question set.

---

## Quick start

### Full — `docker compose up`

Brings up the whole system from a clean checkout: the FastAPI service, the Studio
dashboard in the browser, and observability. On first build it **downloads the
embedding model (BGE-M3) locally** so retrieval runs on-box; the **LLM stays
remote** via your configured gateway (nothing about the language model is
downloaded).

```bash
cp .env.example .env          # LLM gateway + Drive credentials
docker compose up --build
```

| Service | URL | What |
|---------|-----|------|
| API | http://localhost:8000/docs | interactive FastAPI (chat, ingest, agents) |
| Dashboard | http://localhost:8001 | Studio cockpit, served to the browser |
| Traces | http://localhost:6006 | Arize Phoenix observability |

> Running from source instead of Docker: `uv sync --extra full` then
> `uv run klerk studio` (or `make api`). Same full feature set.

### Lite — `pip install`

Runs the agent and the full dashboard against a **remote** embedding endpoint, so
nothing is downloaded and it fits on a laptop, a small VPS, or a phone. The LLM
gateway and Drive work exactly as in the full build.

```bash
pip install -e ".[lite]"
export KLERK_EMBED_BACKEND=remote KLERK_EMBED_REMOTE_URL=… KLERK_EMBED_REMOTE_MODEL=…
klerk chat                    # full-panel cockpit; add --compact for tiny terminals
```

---

## How it works

```
        ┌──────────────────── one engine, two surfaces ─────────────────────┐
        │  FastAPI :8000  ·  Studio TUI (terminal + textual-serve :8001)    │
        └───────────────────────────────┬──────────────────────────────────┘
                                         │  in-process calls (no subprocess hop)
              ┌──────────────────────────┴──────────────────────────┐
              │  Agent loop — ReAct router + sliding-window memory   │
              │  + long-term identity / recalled facts               │
              └──────────────────────────┬──────────────────────────┘
            ┌───────────────┬────────────┼────────────┬───────────────┐
            ▼               ▼            ▼            ▼               ▼
       search_hybrid   scan_conflicts  extract     draft_doc      drive_sync
       (RAG)           (LangGraph)     _actions    (LangGraph)    (incremental)
            │
   ┌────────┴─────────────────────────────────────────────────────────────┐
   │  Retrieval:  Docling parse → chunk → BGE-M3 embed → LanceDB           │
   │              (vector + Tantivy BM25) → RRF fusion → ColBERT rerank    │
   └──────────────────────────────────────────────────────────────────────┘
            │
   ┌────────┴───────────────────────────┐
   │  LLM gateway (LiteLLM)             │  ← self-hosted only; env-configured
   └────────────────────────────────────┘
```

The chat loop's tools run **in-process** (one model load per deployment, no
per-call subprocess overhead). The same underlying functions are also exposed as
CLI verbs — the *external* contract for non-Python callers. Full diagram and
rationale in [docs/architecture.md](docs/architecture.md).

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| API | **FastAPI** + Pydantic | async, typed, auto OpenAPI |
| Agent orchestration | **LangGraph** (multi-step flows) + **PydanticAI** (typed one-shots) | graph where state matters; typed calls everywhere else |
| LLM gateway | **LiteLLM** → self-hosted endpoint | one config-driven entry point, no vendor lock-in |
| Embeddings | **BGE-M3** (local) or any OpenAI-compatible endpoint (remote) | multilingual, 1024-d, Bahasa-strong; pluggable |
| Vector store | **LanceDB** (embedded) | vector + lexical search in one process, no sidecar DB |
| Retrieval | hybrid (vector + **Tantivy** BM25) → **RRF** → **ColBERT** rerank | recall *and* precision; reranker reuses the embedder weights |
| Parsing | **Docling** (PyMuPDF fallback) | layout-aware across PDF/DOCX/MD/TXT |
| UI | **Textual** + **textual-serve** | terminal and browser from one Python codebase |
| CLI | **Typer** with `--agent/--json` | human tables + machine JSON |
| Observability | **Arize Phoenix** (OpenTelemetry) | spans for every retrieval + LLM call |
| Eval | custom rubric + **RAGAS** | repeatable, zero-cost scoring |
| Tooling | **uv**, **Docker**, **pytest** (247 tests) | reproducible builds + a real test suite |

---

## Usage

**Chat** — `uv run klerk chat` (terminal), `uv run klerk studio` (full cockpit),
or `POST /chat` (SSE stream with citations).

**Core CLI verbs** (all support `--agent/--json`):

| Verb | Does |
|------|------|
| `klerk chat` / `klerk studio` | interactive agent (TUI) |
| `klerk search hybrid "<q>"` | one-shot hybrid retrieval |
| `klerk extract-actions <src>` | structured action items from a doc |
| `klerk contradict scan` | cross-document conflict report |
| `klerk escalate draft "<q>"` | structured escalation email for a low-confidence question |
| `klerk drive sync` / `upload` | incremental Drive ingest / push |
| `klerk index build --src <dir>` | parse → chunk → embed → index |
| `klerk memory recall "<q>"` | query long-term memory |
| `klerk eval run` | run the evaluation harness |

**API** — `/chat`, `/ingest`, `/sync-status`, `/health`, plus agent routes
(`/conflicts/scan`, `/actions/extract`, `/draft`, `/drift/*`). See `/docs`.

---

## Generate a sample corpus

No documents yet? klerk can generate a realistic company corpus to demo against —
HR policies, technical SOPs, meeting minutes with action items, FAQs, and org
charts, in English and Bahasa Indonesia, across PDF/DOCX/MD — then push it to
Drive:

```bash
uv run klerk synth gen                                   # generate the documents
uv run klerk index build --src data/synth/fata_organa    # index them
uv run klerk drive upload data/synth/fata_organa --to "$DRIVE_FOLDER_ID"
```

---

## Configuration

All configuration is via environment variables (see [`.env.example`](.env.example)) —
nothing is hardcoded. Key settings:

| Variable | Purpose |
|----------|---------|
| `LITELLM_KEY`, `PROXY_URL`, `CF_CLIENT_ID/SECRET` | LLM gateway endpoint + auth |
| `KLERK_EMBED_BACKEND` | `local` (BGE-M3) · `remote` (OpenAI-compatible) · `mock` |
| `GOOGLE_APPLICATION_CREDENTIALS`, `DRIVE_FOLDER_ID` | Drive service account + folder |

**Install profiles:** `lite` (agent + remote embed — torch-free, ~190 pkgs) ·
`synth` (corpus generator) · `server` (FastAPI + dashboard) · `local` (local
BGE-M3 + torch) · `parse` (Docling) · `eval` (RAGAS) · `obs` (Phoenix) ·
`mcp` (MCP server) · `full` (everything, the Docker default).

---

## Roadmap

klerk today is a self-hosted, single-workspace agent. Where it's headed:

- **Self-serve Drive connect** — OAuth flow so any user can link their own Drive
  (today: service account).
- **Pluggable LLM backends** — bring-your-own OpenAI-compatible gateway alongside
  the self-hosted default.
- **Omni-channel chat** — talk to your documents from **WhatsApp, Telegram, and
  Slack**, not just the API/TUI, so the assistant meets teams where they already
  work.
- **Continuous sync** — live Drive change-watch instead of on-demand incremental
  pulls.
- **Multi-tenant workspaces** — auth + per-team isolation for shared deployments.
- **Deeper personalization** — memory-driven preferences and per-user context.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/architecture.md](docs/architecture.md) | Full architecture + data flow |
| [docs/design-decisions.md](docs/design-decisions.md) | Why these choices (incl. the embedder/reranker evaluation) |
| [DATA_GENERATION.md](DATA_GENERATION.md) | How the sample corpus is generated + QC |
| [EVAL.md](EVAL.md) | Evaluation methodology, rubric, and results |
| [docs/ASSIGNMENT.md](docs/ASSIGNMENT.md) | Take-home brief mapping + compliance |

---

## Limitations & hardware

- **LLM gateway dependency** — generation requires reachable, configured LLM and
  (in local mode) embedding models; klerk explains slow/unavailable inference
  rather than hanging.
- **LLM-as-judge bias** — the eval judge shares the generation model, so absolute
  scores skew optimistic; per-category deltas are the reliable signal (see
  [EVAL.md](EVAL.md)).
- **First local run** downloads ~2GB of BGE-M3 weights (skip entirely with
  `KLERK_EMBED_BACKEND=remote`).

| Resource | Local (full) | Lite (remote embed) |
|----------|--------------|---------------------|
| RAM | ~4GB peak (8GB recommended) | <1GB |
| GPU | optional (`KLERK_EMBED_DEVICE=cuda:0` for speedup) | none |
| Disk | ~3.5GB (image + weights) | minimal |

CPU-only x86_64 / aarch64; tested under Linux 6.x. GPU is never required.

---

## License

MIT. The sample "Fata Organa Solusi" corpus and evaluation set are synthetic and
do not represent any real organisation.
