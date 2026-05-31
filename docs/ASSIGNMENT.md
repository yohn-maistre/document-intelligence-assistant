# Take-home brief mapping

> This document maps **klerk** to the PT Fata Organa Solusi *Middle AI Engineer*
> take-home brief. The main [README](../README.md) describes klerk as a product;
> this file is the point-by-point compliance record for the assignment.

## Context

Build a production-ready Document Intelligence Assistant for a fictional
Indonesian-Japanese tech firm: ingest from Google Drive, RAG over a synthetic
corpus, serve via FastAPI, use **only** the provided self-hosted LLM
(`nemotron-3-nano-omni` over a private LiteLLM + Cloudflare Access gateway), ship
≥1 agentic capability, evaluate against an own 20-question set, and run via
`docker compose up`.

## Must-Have (pass/fail) — coverage

| # | Requirement | Status | Where |
|---|-------------|--------|-------|
| 1 | Drive: Service Account auth, `POST /ingest`, **incremental** sync, format diversity | ✅ | `src/klerk/drive/sync.py`, `tests/test_drive_sync.py` |
| 2 | RAG: chunking + embeddings + vector store + top-k **and an improvement** | ✅ | hybrid (vector+BM25) + RRF + ColBERT rerank — `src/klerk/rag/` |
| 3 | All generation via the provided LLM, env-configured, graceful latency | ✅ | `src/klerk/llm/` (no fallbacks) |
| 4 | FastAPI `/chat` `/ingest` `/sync-status` `/health`, async + Pydantic | ✅ | `src/klerk/api/server.py` |
| 5 | ≥1 agentic capability from A / B / C | ✅✅✅ | **all three** — see below |
| 6 | 20-Q eval set + EVAL.md + ≥1 automated metric + honest failures | ✅ schema · ⏳ numbers | `evaluation_set.json`, [`../EVAL.md`](../EVAL.md) |
| 7 | `docker compose up` brings up the full system | ✅ | `Dockerfile`, `docker-compose.yml` |
| 8 | README + EVAL.md + DATA_GENERATION.md | ✅ | repo root + `docs/` |

### Agentic capabilities (brief menu A / B / C)

| Option | klerk | Surface |
|--------|-------|---------|
| **A — Escalation Drafter** | low-confidence question → structured `{to, subject, body, cc}` | `klerk escalate draft`, inline in `/chat` |
| **B — Action Item Extractor** | meeting text → `{owner, task, deadline, source_doc}` JSON | `klerk extract-actions`, `POST /actions/extract` |
| **C — Conflict Reporter ★** | contradictory chunks → both sides with timestamps + newest-vs-older framing | `klerk contradict scan`, `POST /conflicts/scan` (4-node LangGraph) |

**★ Conflict Reporter is the flagship**, integrated into both the chat agent and
the dashboard. All three options are implemented because the corpus supports them
cheaply.

### Beyond the brief (labeled honestly)

These go past what the brief asks; they are clearly separated so they read as
intentional depth on a solid MVP, not scope creep:

- **Long-term memory** — persistent identity + recalled facts across sessions.
- **Doc-writer** — a multi-stage adversarial drafting graph (`POST /draft`).
- **Knowledge graph + drift monitor** — entity/relation extraction and scheduled
  corpus-change detection.
- **Studio dashboard** — a Bloomberg-style terminal/browser cockpit.
- **Agent-friendly CLI contract** — `--agent/--json` on every verb.

## Should-Have — coverage

SSE streaming ✅ · citations with doc/section/snippet/confidence ✅ · Bahasa
answers ✅ (2 eval items) · conflict awareness ✅ · latency reporting (TTFT +
total) ✅ · env-only config ✅ · graceful degradation ✅ · ≥3 unit tests ✅ (247).

## Nice-to-Have — coverage

Frontend ✅ (Textual dashboard; Streamlit stub left as a pointer) · cross-encoder
reranking ✅ (ColBERT head) · hybrid BM25+vector ✅ · caching + structured logging
+ task runner ✅. *(The brief warns against over-engineering — these are kept
clearly secondary to the MVP.)*

## Honest caveats

- **Eval numbers + the connectivity confirmation** are produced by running the
  pipeline against the live gateway (see [RUNBOOK](RUNBOOK.md)); methodology in
  EVAL.md is final, numbers are filled from an actual run.
- **`docker compose up --build`** is configured and statically validated; the
  full image build is exercised on a network without registry restrictions.
- **LLM-as-judge** shares the generation model — absolute eval scores skew
  optimistic; per-category deltas are the reliable signal.

## Submission checklist

- [ ] Public GitHub repo URL
- [ ] Drive folder ID (corpus uploaded, shared with `ydharmaw@fata-organa.com`, Editor)
- [ ] Self-assessment (strongest / weakest)
- [ ] Hardware tested on (RAM / CPU / GPU / OS)
- [ ] Confirm successful connection to the provided LLM environment
