# v6 plan — Stack C locked

## Reorient

v5 shipped (steps 1-11). Branch `claude/agent-framework-planning-jJqQj`
at `29fc6b8`. Working tree clean. 143 tests green.

v6 = **Stack C**: Python-only orchestrator (LangGraph) for the FastAPI
submission path; Pi promoted from `experimental/` as a second polished
CLI surface (`klerk chat`) backed by the existing klerk FastAPI internal
endpoints.

---

## Architecture target

```
                         ┌────────────────────────────────────┐
                         │  LangGraph Chat Orchestrator       │
   Studio TUI            │  create_react_agent + state graph  │
   (Textual, Python)─────│  sliding-window compaction         │
   HTTP/SSE              │  6 tools dispatched as graph nodes │
                         └────────┬───────────────────────────┘
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

                            ─ ─ ─ ─ ─ ─ ─ ─

   Second CLI surface (promoted from experimental/):

   klerk-cli (npm, TS)
   ──────────────────
   Pi 0.78+ SDK ─── pi-extension-klerk (native TS tools, NO MCP)
                              │
                              ▼
                   HTTP → FastAPI internal tool endpoints
                          (same Python functions the orchestrator routes)
```

**SSE event stream** (downward-compatible with v5):

```
data: {"event": "tool_call",   "name": "search_hybrid", "args": {...}}
data: {"event": "tool_result", "name": "search_hybrid", "summary": "12 chunks"}
data: {"event": "token",       "text": "..."}              # unchanged
data: {"event": "citations",   "citations": [...]}         # unchanged
data: {"event": "session",     "session_id": "..."}        # NEW, first frame
data: {"event": "done",        "ttft_ms": ..., ...}        # unchanged
```

---

## Locked scoping decisions

1. **LangGraph orchestrator** — `create_react_agent` graph; tool-routing
   loop with MAX_TOOL_HOPS=4 safety cap. Replaces the v5 single-shot
   `/chat` RAG handler.
2. **Multi-turn memory** — server-side `SessionStore` (JSONL per session)
   + sliding-window compaction (last 3 turns verbatim; older turns
   summarised into a single system message). Token budget 16K.
3. **doc_writer rename** — `proposal_pipeline.py` → `doc_writer.py`;
   CLI verb `klerk propose` → `klerk write`; skill manifest, README,
   HANDOFF, MCP server tool name all updated.
4. **doc_writer as LangGraph sub-graph** — 7 stages become explicit
   nodes; checkpoints stored under `.klerk/checkpoints.db`.
5. **PydanticAI migration** — `action_items.py`, `kg_extract.py`, and
   `contradiction.judge_pair()` migrated from raw-LiteLLM JSON-schema to
   `Agent(result_type=PydanticModel)`. Closes the v5 docs/reality gap.
6. **Pi as 2nd surface** — `experimental/ts-shell/` graduates to
   top-level `cli/` (or `pi-surface/`); `pi-extension-klerk` rewritten
   to use Pi's native `defineTool()` typebox API (no MCP, per Pi's
   "No MCP" design stance); both packages migrate from
   `@mariozechner/pi-coding-agent@0.73.1` → `@earendil-works/*` latest.
7. **Lite TUI right rail = five widgets**: corpus stats, activity (tool
   calls), recent traces (chat exchanges), eval header (rubric mean),
   sessions (start new / list recent).
8. **Drive upload includes `--dry-run`**.
9. **Remote embed backend** = provider-neutral via env-var
   (`KLERK_EMBED_REMOTE_URL` + `KLERK_EMBED_REMOTE_KEY` +
   `KLERK_EMBED_REMOTE_MODEL`). `.env.example` lists DeepInfra / Jina /
   OpenRouter as known-compatible.
10. **No remote reranker** — remote mode = RRF-only; local mode keeps
    BGE-M3 ColBERT MaxSim. Rerank module gracefully falls back when
    ColBERT vectors are unavailable.

---

## Implementation order (~22h)

### Cluster 1 — Backend foundations (~3h)

#### 1.1 Remote embed backend  (~1h)
- `src/klerk/rag/embed.py`: `_backend()` recognises `"remote"`;
  `_remote_embed()` POSTs OpenAI-compat `/embeddings` with Bearer auth;
  fails clearly on dim ≠ 1024.
- `embed_with_colbert` raises `RuntimeError("ColBERT vectors unavailable
  in remote mode")`.
- Tests: `tests/test_embed_remote.py` (mock httpx, verify routing,
  dim contract, ColBERT error path).

#### 1.2 Rerank: graceful fallback  (~15min)
- `src/klerk/rag/rerank.py`: wrap `embed_with_colbert([query])` in
  try/except; on the documented RuntimeError, return passages in RRF
  order + log one-line warning.

#### 1.3 Drive upload verb with `--dry-run`  (~1.5h)
- `src/klerk/drive/sync.py`: `UPLOAD_SCOPE = "...drive.file"`;
  `_service_for_upload()` factory; `upload_file()` via `MediaFileUpload`
  + `mimetypes.guess_type`; `upload_directory(..., dry_run)`.
- `src/klerk/cli/drive_cmd.py`: `klerk drive upload --src --to --glob
  --skip-existing --dry-run`.
- Tests: mocked service, duplicate-skip, dry-run never calls API.

### Cluster 2 — doc_writer rename + LangGraph refactor (~2h)

#### 2.1 Rename `proposal_pipeline` → `doc_writer`  (~30min)
- `src/klerk/agent/proposal_pipeline.py` → `doc_writer.py`
- CLI: `klerk propose` → `klerk write`
- MCP tool name: `propose` → `draft_doc`
- Skill manifest: `src/klerk/agent/skills/propose.yaml` →
  `draft_doc.yaml`
- README, HANDOFF, docs/architecture.md, evaluation_set.json, golden.py
  call-sites
- `tests/test_proposal_pipeline.py` → `test_doc_writer.py`; assertions
  updated

#### 2.2 LangGraph refactor of doc_writer  (~1.5h)
- New `src/klerk/agent/doc_writer_graph.py`: `StateGraph` with nodes
  `scope → drafter_a ‖ drafter_b → citation_tracer → adjudicator →
  critic`. Parallel A/B drafters as a fan-out edge.
- State schema: `DocWriterState(topic, sections, draft_a, draft_b,
  citations, winner, rubric_scores)`.
- SQLite checkpointer under `.klerk/checkpoints.db` (table:
  `doc_writer`); `klerk write --resume <run_id>`.
- `doc_writer.py` becomes a thin entry calling the graph.

### Cluster 3 — PydanticAI migration (~1.5h)

#### 3.1 `action_items.py` migration  (~30min)
- Define `class ActionItem(BaseModel)` and `class
  ActionItemList(BaseModel)`.
- Replace raw LiteLLM + JSON-schema with
  `Agent(model=..., result_type=ActionItemList)`.
- Wire Nemotron via PydanticAI's `OpenAIModel` (proxy URL + CF headers).

#### 3.2 `kg_extract.py` migration  (~30min)
- Define `class Entity / Relation / KGSnippet(BaseModel)`.
- Same migration pattern.

#### 3.3 `contradiction.judge_pair()` migration  (~30min)
- Define `class ConflictVerdict(BaseModel)`.
- Same migration pattern.
- Tests: update assertions for typed objects, drop manual JSON parsing.

### Cluster 4 — Multi-turn chat orchestrator (~5h)

#### 4.1 `SessionStore` + sliding-window compaction  (~1.5h)
- `src/klerk/api/session.py` (~120 LOC, NEW)
- `.klerk/sessions/{session_id}.jsonl`, one line per turn.
- `build_prompt_history(session_id, max_tokens=16000) -> list[Message]`:
  keep last 3 turns verbatim; summarise turns 4..N via small Nemotron
  call ("Summarise in ≤200 tokens, preserve entities/decisions"); cache
  summary keyed by `(session_id, last_summarised_turn)`.
- `tests/test_session_store.py` (NEW): write/read, compaction trigger,
  summary cache hit.

#### 4.2 LangGraph orchestrator + 6 tools  (~3h)
- `src/klerk/agent/orchestrator.py` (~200 LOC, NEW): `create_react_agent`
  wrapped to emit SSE events through a callback handler.
- `src/klerk/agent/tools.py` (~150 LOC, NEW): 6 tools registered as
  LangChain tools wrapping existing Python functions:
  `search_hybrid`, `extract_actions`, `draft_doc`, `scan_conflicts`,
  `ingest_path`, `sync_drive`. Each has a `display_name` like
  `"klerk search hybrid"` for the Activity UI.
- System prompt update in `src/klerk/agent/prompts/system.py`: enumerate
  the 6 tools with selection guidance.
- Pre-seed `search_hybrid` results into every turn so even a no-tool LLM
  response is grounded.
- `MAX_TOOL_HOPS=4` safety cap; truncation marked in `done` event.
- Tests: `tests/test_orchestrator.py` (~150 LOC, NEW) — golden-tape style
  fixtures, mocked LLM tool calls, fallback-to-RAG path.

#### 4.3 `/chat` handler rewire  (~30min)
- `src/klerk/api/server.py`: `_chat_event_stream` calls
  `orchestrator.arun()` instead of inline RAG-then-LLM logic. All event
  types flow through `EventSourceResponse` unchanged.
- `ChatRequest` gains `session_id: str | None` and
  `history_mode: "auto" | "off"`.
- `tests/test_api_endpoints.py` updated to allow new event types.

### Cluster 5 — Studio TUI upgrade (~4h)

#### 5.1 `LiveChatPanel` widget  (~1.5h)
- `src/klerk/studio/widgets/live_chat.py` (~200 LOC, NEW).
- Input + scrollable `MessageLog`; on submit, opens SSE stream to
  `${KLERK_API_URL:-http://localhost:8000}/chat`.
- Event handlers for `session`, `tool_call`, `tool_result`, `token`,
  `citations`, `escalation`, `done`. Tool cards collapse/expand.
- `session_id` held as panel state; persists across messages.

#### 5.2 `ActivityBlock` widget  (~45min)
- `src/klerk/studio/widgets/activity.py` (~80 LOC, NEW).
- Reads `.klerk/activity-log.jsonl` (orchestrator appends one line per
  tool call with ts, session_id, tool, status, duration).
- Renders last 5 entries; refresh every 3s.
- Line format:
  `[14:23:01] 🔍 klerk search hybrid "exit criteria" → 12 chunks (847ms)`

#### 5.3 `SessionPanel` widget  (~30min)
- `src/klerk/studio/widgets/sessions.py` (~60 LOC, NEW).
- List active + 5 most-recent sessions from `.klerk/sessions/`.
- Buttons: "New chat" (issues a new session_id to LiveChatPanel),
  "Switch to" (loads selected session's history into LiveChatPanel).

#### 5.4 Lite TUI layout + full-Studio Chat upgrade  (~1.5h)
- `src/klerk/studio/app.py`:
  - `LiteShell(Container)` — 2/3 + 1/3 grid:
    - Left: `LiveChatPanel`
    - Right rail (5 stacked widgets): `SessionPanel`,
      `CorpusStatBlock`, `ActivityBlock`, `RecentTracesBlock`,
      `EvalHeaderBlock`
  - Full Studio Chat tab: embed `LiveChatPanel`; the chat-history tail
    (current `chat-history.jsonl` reader) becomes a "Prior sessions"
    collapsible above the live input. Hidden by default; shown when
    `KLERK_TUI_SHOW_HISTORY=1` or `klerk studio --with-history`.
- `--lite` CLI flag on `klerk studio`.

#### 5.5 `--serve` unstub  (~45min)
- `src/klerk/cli/main.py` (lines 113-118): replace stub with
  `subprocess.run(["uv", "run", "textual", "serve",
   "klerk.studio.app:main", *extra_args])`.
- Add `textual-serve>=1.1` to `pyproject.toml`.
- `--serve` combinable with `--lite` and `--with-history`.

### Cluster 6 — Pi as 2nd CLI surface (~3h)

#### 6.1 `pi-extension-klerk` rework: native TS tools, no MCP  (~1.5h)
- `experimental/pi-extension/src/tools/` rewrite each TS file to register
  via Pi's `defineTool()` typebox shape (Pi 0.78+).
- Each tool's `execute()` POSTs to a klerk FastAPI internal endpoint
  (e.g. `/internal/search_hybrid`) and streams the response back.
- Add `/internal/*` endpoints to `src/klerk/api/server.py` (~80 LOC) —
  same Python functions the orchestrator routes, exposed for the Pi
  surface and other MCP-less clients.
- Delete the `klerk-mcp` system-prompt reference; system prompt now
  describes tools directly.

#### 6.2 Migrate to `@earendil-works/*`  (~30min)
- `experimental/pi-extension/package.json`: peer dep
  `@earendil-works/pi-coding-agent@^0.78`.
- `experimental/ts-shell/package.json`: dep
  `@earendil-works/pi-coding-agent@^0.78`.
- `pnpm install`; verify `dist/index.d.ts` API still matches our
  integration; update import paths if needed.

#### 6.3 Promote `ts-shell` from experimental/  (~30min)
- `experimental/ts-shell/` → `cli/` at repo root.
- Update `experimental/README.md` to remove the ts-shell entry; explain
  pi-extension still lives in experimental/ as a downstream-publishable
  npm package.
- `cli/README.md` — install + usage docs (`pnpm install -g @yohnmaistre/
  klerk-cli && klerk chat`).
- `cli/package.json`: bump version to `0.1.0`; `name` confirmed
  `@yohnmaistre/klerk-cli`.

#### 6.4 npm publish prep  (~30min)
- Polish `cli/package.json` `files`, `exports`, `bin`, `repository`,
  `keywords`.
- `pnpm pack` smoke-test; verify the tarball contains only `dist/`,
  `bin/`, `skills/`, and no `node_modules`.
- Document the publish steps in HANDOFF (don't actually publish yet —
  defer to post-submission).

### Cluster 7 — Demo + docs (~2.5h)

#### 7.1 `Makefile`: `demo-lite` target  (~30min)
```make
demo-lite: ## Lite TUI in browser; remote embeddings; docker-backed API
	@test -n "$$KLERK_EMBED_REMOTE_URL" || (echo "set KLERK_EMBED_REMOTE_URL — see .env.example" && exit 1)
	@test -n "$$KLERK_EMBED_REMOTE_KEY" || (echo "set KLERK_EMBED_REMOTE_KEY" && exit 1)
	@test -n "$$KLERK_EMBED_REMOTE_MODEL" || (echo "set KLERK_EMBED_REMOTE_MODEL" && exit 1)
	KLERK_EMBED_BACKEND=remote uv run klerk studio --lite --serve
```

#### 7.2 README sweep  (~1h)
- New "Agentic chat orchestrator" section — describe LangGraph
  `create_react_agent`, tool surface, event stream.
- New "Deployment shapes" section — three-shape table:
  | Shape | TUI | Backend | When |
  |Docker workstation|Full Studio|Local Docker|Primary submission|
  |Lite + browser|Lite Studio|Local Docker or remote embed|Reviewer constrained env|
  |Pi CLI|`klerk chat` (Pi 0.78+)|Local FastAPI via /internal/*|Developer chat|
- Update architecture diagram (TUI ↔ FastAPI ↔ orchestrator ↔ tools).
- Update design-influences: `Hermes (single-loop ReAct)` row removed
  (orchestrator is now LangGraph, not single-loop); `OpenClaw (workflow
  shape)` row points to doc_writer (renamed); add `Pi (chat surface)`
  row with link.

#### 7.3 `DATA_GENERATION.md` §10  (~15min)
- `klerk drive upload` walkthrough (real + `--dry-run`).

#### 7.4 `.env.example` update  (~15min)
- Add `KLERK_EMBED_BACKEND`, `KLERK_EMBED_REMOTE_URL`,
  `KLERK_EMBED_REMOTE_KEY`, `KLERK_EMBED_REMOTE_MODEL` block with
  DeepInfra / Jina / OpenRouter examples.

#### 7.5 HANDOFF.md v6 section  (~30min)
- New section 12. v6 plan summary (mirrors this file at lower fidelity).

### Cluster 8 — Commits + merge (~30min)

6 commits on `claude/agent-framework-planning-jJqQj`:

1. `refactor: rename proposal_pipeline → doc_writer`
2. `feat(remote): KLERK_EMBED_BACKEND=remote OpenAI-compat`
3. `feat(drive): klerk drive upload with --dry-run`
4. `feat(pydantic-ai): migrate action_items + kg_extract +
   contradiction.judge_pair`
5. `feat(agent): LangGraph orchestrator + sliding-window memory + doc_writer
   graph + 6 tools + lite TUI + --serve + demo-lite`
6. `feat(pi-surface): promote klerk-cli; pi-extension on native tools;
   @earendil-works migration`

Then merge to `main`.

---

## Explicitly out of scope (v7+)

- **PydanticAI for the orchestrator.** Staying LangGraph for v6; revisit
  if a second orchestrator lands.
- **Pi as the primary orchestrator** (Stack A). Documented in v6 plan
  rationale; defer unless Stack C UX feedback says otherwise.
- **Remote ColBERT-aware rerank** (Jina multi-vector + local MaxSim).
- **Quantised BGE-M3** (INT8 ONNX) as a third backend tier.
- **Drift agent as a routable tool** — it's an APScheduler background
  loop, not a user-initiated action.
- **Self-hosted Modal/Vespa deployment templates.**
- **OAuth alternative** to Drive Service Account.
- **`/conflicts/scan?resume=run_id`** (LangGraph resumption surface).
- **Publishing `klerk-cli` to npm.** Defer to post-submission. The
  package is publish-ready locally.

---

## File touch list

```
src/klerk/rag/embed.py                       (+~60 LOC)   remote backend
src/klerk/rag/rerank.py                      (+~10 LOC)   ColBERT fallback
src/klerk/drive/sync.py                      (+~80 LOC)   upload_* + drive.file scope
src/klerk/cli/drive_cmd.py                   (+~40 LOC)   upload verb + --dry-run

src/klerk/agent/proposal_pipeline.py → doc_writer.py     rename
src/klerk/agent/doc_writer_graph.py          (NEW ~200)   LangGraph spine
src/klerk/agent/skills/propose.yaml → draft_doc.yaml     rename
src/klerk/cli/main.py: klerk propose → klerk write       rename

src/klerk/agent/action_items.py              (~−40 +~30)  PydanticAI
src/klerk/agent/kg_extract.py                (~−50 +~40)  PydanticAI
src/klerk/agent/contradiction.py             (~−30 +~25)  judge_pair PydanticAI

src/klerk/api/session.py                     (NEW ~120)   SessionStore + sliding window
src/klerk/api/server.py                      (~−80 +~150) /chat → orchestrator + /internal/*
src/klerk/api/models.py                      (+~15 LOC)   session_id / history_mode

src/klerk/agent/orchestrator.py              (NEW ~200)   LangGraph create_react_agent
src/klerk/agent/tools.py                     (NEW ~150)   6 tool definitions
src/klerk/agent/prompts/system.py            (+~25 LOC)   orchestrator system prompt

src/klerk/studio/app.py                      (+~120 LOC)  LiteShell + Chat tab upgrade
src/klerk/studio/widgets/live_chat.py        (NEW ~200)
src/klerk/studio/widgets/activity.py         (NEW ~80)
src/klerk/studio/widgets/sessions.py         (NEW ~60)
src/klerk/cli/main.py                        (+~30 LOC)   --serve + --lite + --with-history

experimental/pi-extension/src/tools/*.ts     (~−200 +~280) native defineTool, no MCP
experimental/pi-extension/src/index.ts       (~−40 +~30)  no klerk-mcp reference
experimental/pi-extension/package.json       (peer dep migration)
experimental/ts-shell/ → cli/                (move)
cli/package.json                             (rename + 0.1.0 bump)
cli/README.md                                (NEW)

tests/test_embed_remote.py                   (NEW ~80)
tests/test_drive_sync.py                     (+~50)
tests/test_session_store.py                  (NEW ~80)
tests/test_orchestrator.py                   (NEW ~150)
tests/test_doc_writer.py                     (renamed from test_proposal_pipeline)
tests/test_action_items.py                   (~−30 +~30)  PydanticAI shape
tests/test_kg_extract.py                     (~−30 +~30)
tests/test_contradiction.py                  (~−20 +~20)
tests/test_api_endpoints.py                  (+~30)       new event types

.env.example                                 (+remote embed block)
Makefile                                     (+demo-lite target)
README.md                                    (~+120 LOC delta)
DATA_GENERATION.md                           (+§10 ~25 LOC)
HANDOFF.md                                   (+§12 ~80 LOC)
docs/architecture.md                         (~+40 LOC)
experimental/README.md                       (~+20 LOC, ts-shell entry removed)
```

20 source files, 5 new test files. Net add ~1900 LOC. All v5 tests stay
green; ~370 LOC of new test coverage.

---

## Risks specific to v6

| Risk | Likelihood | Mitigation |
|---|---|---|
| Nemotron tool-routing unreliable (LangGraph picks wrong tool) | Medium | Pre-seed `search_hybrid` results every turn; explicit tool-selection prompt; fallback path keeps system useful |
| LangGraph + LiteLLM tool-call shape mismatch | Low-Medium | LangGraph 0.2+ supports OpenAI-format tool calls; LiteLLM translates Nemotron → OpenAI tool-call format |
| Pi `@earendil-works/*` API drift from 0.73 → 0.78 | Medium | Verify `dist/index.d.ts` matches integration; pin to exact 0.78.x for v6; rebrand still in flight |
| PydanticAI Nemotron-via-OpenAI-proxy edge cases | Low | OpenAIModel accepts custom `base_url` + `http_client` headers; standard pattern |
| Sliding-window summary cost (extra Nemotron call per overflow turn) | Low | Cached by `(session_id, last_summarised_turn)`; summary call is small (~200 token output) |
| LiveChatPanel SSE backpressure with slow Nemotron | Low | Textual reactive widgets handle async; no event loop blocking |
| Drive upload accidentally targets wrong folder | Low (mitigated) | `--dry-run` printed before live; `--to` is mandatory; drive.file scope limits blast radius |

---

## Decision log

Captured for future-session pickup so the rationale survives the
conversation buffer. One subsection per architecturally consequential
choice.

### Why LangGraph for the orchestrator (not Pi, not PydanticAI alone)

- LangGraph gives state-machine semantics for tool routing + sub-graph
  composition. v5 already proved this on the 4-node conflict scanner
  and (informally) on the 7-stage doc_writer. Mature, OpenAI-tool-call
  format, LiteLLM-compatible.
- **Pi** was researched seriously (mariozechner/pi-coding-agent, now
  `@earendil-works/*`): excellent agent core (built-in compaction,
  multi-session JSONL, branching/forking, 25+ provider support, 4
  surface modes — TUI / print-JSON / RPC / SDK). **Rejected as
  PRIMARY** orchestrator: it's a Node sidecar; running it from FastAPI
  requires a JSONL bridge or RPC tax, plus a Node runtime in Docker.
  That's a 4-process hop per tool call and brittle plumbing.
- **PydanticAI** alone: lacks the state-machine semantics for the
  7-stage doc_writer / 4-node conflict scanner. We use it for one-shot
  agents (action_items, kg_extract, contradiction.judge_pair) where
  typed outputs matter and graph structure doesn't.

### Why Pi as a 2nd surface (and why not Stack A)

- Pi already exists in `experimental/` (pi-extension + ts-shell
  investment from earlier sessions). Throwing it away to go pure-Python
  wastes that work; promoting it gives a 2nd polished CLI surface
  basically free, and Pi's TUI is genuinely better than what we'd build
  in Textual for the terminal-chat use case.
- Pi as PRIMARY (Stack A) rejected for reasons above.
- Pi as 2ND SURFACE (Stack C): runs out-of-band, talks to FastAPI
  `/internal/*` over HTTP, no Docker impact, both surfaces reuse the
  same Python tool functions. No double-implementation of business
  logic.
- The 2nd surface is positioned for developers who prefer terminal-
  native chat over the Studio TUI. Not a substitute for the Studio
  TUI — they ship together.

### Why rename `proposal_pipeline` → `doc_writer`

- The brief frames the agentic menu as Escalation Drafter / Action Item
  Extractor / Conflict Reporter. "Doc writer" matches that vocabulary;
  "proposal" is one specific use case out of many (SOPs, escalations,
  FAQs, etc.).
- CLI verb `klerk propose` → `klerk write` matches mental model better.
- MCP tool name `propose` → `draft_doc` is more generic and pairs with
  `search_hybrid`, `extract_actions`, `scan_conflicts`.

### Why close the pydantic-ai gap now

- Architecture review found pydantic-ai in `pyproject.toml` deps but
  `grep "pydantic_ai" src/` returned 0 hits. Docs claimed we used it
  in `action_items` and `kg_extract`; reality used raw LiteLLM +
  JSON-schema. Either remove from deps or actually use it.
- Decided to **use** it for the 3 one-shot agents (action_items,
  kg_extract, contradiction.judge_pair). Typed Pydantic outputs are a
  clean fit; the migration is ~80 LOC net change and earns docs/reality
  parity.

### Why migrate to `@earendil-works/*` now

- The `pi-coding-agent` rebrand is in flight (badlogic + mitsuhiko's
  org). 0.78+ ships under `@earendil-works/`. The current 0.73 pin
  under `@mariozechner/` is going stale.
- Doing the bump as part of the Pi promotion is one less migration
  later; the API drift between 0.73 and 0.78 is small and verified
  ahead of integration.

### Why three deployment shapes (and not just one)

- Brief mandates Docker + `docker compose up`. That's shape 1 (full
  Studio TUI + local backend).
- Reviewer may evaluate in a constrained env (no Docker GPU, slow
  install). Shape 2 (Lite Studio via `textual-serve` + remote embed
  backend) gets them running in a browser in <2min.
- Shape 3 (Pi CLI) is the developer surface — not on the reviewer
  path, but the npm package is publish-ready as a portfolio artifact.

### Rejected alternatives (do not revisit without new evidence)

- **Stack A** (Pi as primary orchestrator): Node sidecar tax on FastAPI.
- **Stack B** (pure LangGraph, scrap Pi): wastes the
  `experimental/pi-extension/` + `ts-shell/` investment.
- **MinerU 2.5** for layout (v3 candidate): 14% non-Latin accuracy drop
  on MDPBench Apr 2026 disqualifies it for Bahasa docs.
- **Semantic LLM cache** (LanceDB-backed): cache-poisoning + audit
  surface area > value for a 25-doc corpus. Exact-match DiskCache only.
- **Flue** (`@flue/runtime` by Schott, built on
  `@earendil-works/pi-agent-core`): researched 2026-05-30. Pure Node /
  Cloudflare framework, no Python embedding path, pre-1.0
  ("Experimental" in README), headless (no built-in TUI). Doesn't
  solve the Python-Node bridge and doesn't fit the polished-CLI-chat
  goal. Not adopted.
- **Headless Pi as the 2nd surface**: Pi already runs headless in RPC
  mode if we ever need it; we picked the TUI mode because polished
  developer chat is the use case. Headless is there as a fallback.

---

## Changelog

Iteration notes. Append on each significant plan revision; future
sessions can scan this for "what changed and why."

### v6.0 — 2026-05-30 (this revision)

**Lock-in**: Stack C (LangGraph Python orchestrator + Pi as 2nd CLI
surface). Multi-turn `/chat` with sliding-window memory. Renames
`proposal_pipeline` → `doc_writer`. PydanticAI migration for three
one-shot agents. Drive upload with `--dry-run`. Remote embed backend
for constrained-env demo path. Lite Studio TUI shape. `klerk-cli` npm
package (publish-ready, don't publish yet).

**Research conducted**:

- Pi SDK inspection: confirmed `createAgentSession`, built-in
  compaction, multi-session JSONL, 25+ providers, 4 surface modes.
  Decision: adopt as 2nd surface, not primary.
- `@earendil-works/*` rebrand: confirmed maintained by Mario Zechner
  + Armin Ronacher; 0.78+ shipping under new org. Decision: migrate
  during Pi promotion.
- Flue (`@flue/runtime` v0.8.1 by Fred K. Schott, built on Pi):
  confirmed real, headless TS framework with Cloudflare DO sessions.
  Decision: not adopted (pure Node, pre-1.0, headless).

**Architecture review gaps closed**:

- pydantic-ai in deps but unused → migrate action_items + kg_extract
  + contradiction.judge_pair.
- proposal_pipeline naming inconsistent with brief framing → rename
  to doc_writer + `klerk write` CLI verb.

**Scope grew from v5 audit**: +Pi 2nd surface (+~3h), +PydanticAI
migration (+~1.5h), +doc_writer rename (+~30min). Total v6 estimate
~22h (was ~13-15h pre-Pi-promotion).

### v5 (prior) — what shipped

Steps 1-11 from `HANDOFF.md` section 7. Branch
`claude/agent-framework-planning-jJqQj` at `29fc6b8` (pre-v6 work).
143 tests green. README rewrite, Streamlit stub, DATA_GENERATION,
Workspace MCP, Studio refactor, LangGraph conflict spine, agentic
capabilities A/B/D/E, evaluation set + golden rewire, synth corpus
generator, Dockerfile + compose, Drive incremental sync.
