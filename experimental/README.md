# experimental/

Code that was implemented during klerk's exploratory phase, then demoted
during the v5 cleanup pass because it falls outside the brief's MUST-have
surface. Kept here (not deleted) so the reasoning is visible and any single
item can be promoted back if a follow-up requires it.

Nothing in `experimental/` is imported by the production package (`src/klerk/`).
Nothing here is part of the `docker compose up` flow. CI does not exercise it.

## What's here, why it was demoted, and what would re-trigger it

### `ts-shell/` (formerly `klerk-cli/`)

A polished TypeScript CLI shell. The original framing was "klerk runs on
hardware" (Pi-as-runtime), with this TS shell delegating to a hidden Python
runtime. The brief is silent on hardware and asks for a FastAPI server, so
the shell is out of scope. We could revive it if a follow-up wants a
distributed-edge story — the chat-runtime abstraction is reusable.

### `pi-extension/` (formerly `pi-extension-klerk/`)

A Pi contributor npm extension. Same rationale as `ts-shell/`: the
Pi-as-runtime narrative is out of brief scope. The extension shape is a
template for any future Pi/npm packaging effort.

### `checkpoint.py`

SQLite-backed checkpoint store for mid-run resumability of long agentic
workflows (the "Dynamic-Workflows" pattern). The brief has no long-running
agentic ops — the agentic capabilities (Escalation, Action Items, Conflict
Reporter, Writer, Drift) all return in seconds. LangGraph (used for the
Conflict Reporter spine in step 8) ships its own SQLite checkpointer for
the one resumable flow we expose. Promote this back if multi-step
human-in-the-loop workflows ever land.

### `pagerank.py`

Personalized-PageRank tiebreaker over the chunk-similarity graph. Ran as
a tertiary signal after vector + BM25 + cross-encoder. The BGE-M3 ColBERT
head (the v5 reranker) already separates near-ties cleanly at the k=8
window we use, so PageRank's marginal gain doesn't justify the ~150ms it
adds. Promote this back if reviewer feedback shows top-k thrashing.

### `seahelm_runner.py`

SEA-HELM-style Bahasa parity reporter (Δ = id_score − en_score per axis).
Overkill for the brief's 2-Bahasa-question evaluation set; the standard
5-axis rubric covers per-locale aggregates already. The runner is here
if we ever want to ship a Bahasa-first variant evaluated against the full
SEA-HELM rubric.

### `background.py`

APScheduler-driven local-filesystem ingestion: watches `data/raw/`,
diffs by sha256, re-indexes changed files. The brief's incremental sync
target is Google Drive (Service Account + `changes.list`), not a local
watch directory — so the APScheduler shell here doesn't transfer directly.
The diff/manifest *pattern* did transfer: the generic `diff_manifest` and
manifest-IO helpers in `src/klerk/drive/sync.py` were extracted from
this file in step 1. The full Drive sync wraps those helpers in step 3.

The Drift agent (capability E) reuses APScheduler via the `[scheduled]`
optional-dependency extra; that re-import is narrow and lives in
`src/klerk/scheduled/drift_runner.py` (created in step 7), not here.
