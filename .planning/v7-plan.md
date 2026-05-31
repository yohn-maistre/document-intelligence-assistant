# klerk v7 — Hermes-paradigm agent + Midday CLI contract + dual-surface (lite/full)

> **Active plan.** Supersedes v6/Stack-D (`.planning/archive/v6-plan.md` + `.planning/archive/stack-d-migration.md`). Drafted 2026-05-30 evening Jakarta after a strategy-session review that surfaced six deltas (D1-D6, §0) to the v6 architecture.
>
> Phase C (TS/Bun rewrite — Flue / Mastra) is **omitted** for v7. LangGraph subgraphs retained. Deadline confirmed **31 May 2026 morning Jakarta** (recruiter-negotiated; user confirmed 2026-05-30 evening).
>
> Plan-mode scratch file (with this v7 plan + archived v4 + post-step-11 plans for full trace) lives at `~/.claude/plans/root-claude-uploads-6b70b1bf-d52d-4f10-imperative-hickey.md` outside the repo.

---

## 0. Deltas applied (2026-05-30 strategy session)

| # | Delta | Where it lands |
|---|-------|----------------|
| D1 | Orchestrator tools are **in-process** Python function calls, not subprocess shell-outs. **One engine per deployment.** CLI `--agent --json` = **external** contract only (Claude Code, cron, manual shell). | §2, §3 choices #2-#3, §7 |
| D2 | Drop `/internal/*` entirely. textual-serve runs Textual server-side as a Python process with in-process engine access — no HTTP shim needed. | §3 diagram, §5, §7 |
| D3 | `/memory/*` HTTP routes are bonus, not floor. CLI verbs + TUI in-process already cover memory ops. | §5 A.2, §6 S2 |
| D4 | `doc_writer` (7-stage LangGraph) reframed as **bonus**. `scan_conflicts` (4-node LangGraph) is the **Brief-Option-C core**. | §3 choices, §5 framing, README |
| D5 | All three brief options A/B/C implemented. KG / drift / doc_writer = labeled "beyond brief." | README + EVAL self-assessment |
| D6 | Studio dashboard sequenced behind floor. **Floor** panes: Chat / Files / Activity / Status / Traces. **Bonus** panes: Eval / KG / Sparklines, with explicit cut order. | §5 A.3, §6 S3 |

**Also done before this plan was written (Phase A.0 partial)**: `claude/handoff-embed-backend-resume-RQYyt` **merged into main via merge commit `740cddd`**. Both `main` and `claude/agent-framework-planning-jJqQj` are at `740cddd` and pushed.

---

## 1. Context

**Today**: 2026-05-30 evening, Jakarta. **Submission deadline**: 31 May 2026 morning Jakarta (recruiter-negotiated from the brief literal date 30 Sep 2026 to a near-term sprint).

**Repo state (post-merge `740cddd`)**:

- `main` and `claude/agent-framework-planning-jJqQj` both at `740cddd` (merge commit). Linear path through `main` v5 + v6 docs lineage; merge brings in the RQYyt 6-code-commit lineage.
- 9,699 LOC Python across `src/klerk/` in 14 subpackages + 2,871 LOC tests across 17 test files (+1,331 src LOC and +909 test LOC from RQYyt vs pre-merge main).
- Docker compose works. `/chat` is **already an agentic Hermes-style react loop** (LangGraph `create_react_agent` + 6 **in-process** tools + SessionStore sliding-window compaction).
- Brief Required-Tech "Optional: Agentic capability" is solidly met. **Brief floor is fully satisfied by main alone.**

**Four-agent research synthesis** (cited in archived `.planning/archive/v6-plan.md` and `.planning/archive/stack-d-migration.md`):

1. **Pi**: vertical-stack TUI only, no horizontal-layout primitives, Node-only. Not viable for multi-pane dashboard. Archived.
2. **Flue (`@flue/sdk` v0.7.0)**: TS rewrite cost 4-6 weeks; kills the Python substrate. Phase C → omitted.
3. **Midday CLI**: dual-mode CLI as **external** contract. The `--agent --json` discipline IS the API. **NOT how the agent calls its own in-process tools** (D1 correction relative to v6 framing).
4. **TS+Bun ecosystem**: LanceDB JS lacks BM25/FTS; LanceDB on Bun is REST-only; no ColBERT in TS; no Tantivy in JS. Bun-on-proot-Debian works fine but the ecosystem gaps are non-negotiable. Phase C omitted.

**Hermes Agent**: hand-rolled Python (Nous Research, Rich-based TUI + JSON-RPC tui_gateway). **NOT Pi-based.** v7 borrows the SOUL.md + MEMORY.md + state.db trio convention for long-term memory.

**Memory verdict**: skip Honcho (AGPL + Postgres + Redis + Deriver worker), skip Letta/Mem0 (extra service surface). Adopt: **LanceDB-backed long-term memory module + Pi's session compaction pattern (already on main via RQYyt SessionStore) + SOUL.md/MEMORY.md file convention from Hermes**. ~180 LOC.

**User vision (verbatim-paraphrased)**: SOTA document intelligence agent — Hermes-kind, not fixed-workflow-kind — with Midday-pattern CLI verbs as the external contract; PydanticAI for fixed processes; embedding model run once (remote for lite, downloadable for full); two polished surfaces — full (`docker compose up` → FastAPI + Studio web) and lite (CLI + local vector DB, no Docker); brief deductions for "outside the box" acceptable if implicit PRD is met.

**Time budget**: ~5h tonight + ~5h tomorrow morning = ~10h wall-clock, across 4 parallel Opus 4.8 sessions (effective ~30-40 agent-hours).

---

## 2. The v7 vision in one paragraph

`klerk` is a **Hermes-style document intelligence agent** whose chat loop holds long-term identity + facts memory (SOUL.md + MEMORY.md + LanceDB recall), whose tools execute **in-process** for hot-path performance (one model load per deployment, no subprocess overhead per turn), and whose UI ships as two surfaces — Textual TUI in terminal and the same TUI served in-browser via `textual-serve` — from one Python substrate. The **CLI verbs are the external tool contract** (Midday `--agent --json` pattern): Claude Code, cron schedules, recruiters' manual shell sessions, and any future TS rewrite all consume klerk via the same JSON-on-stdout discipline. Internally, the orchestrator imports core modules directly via `src/klerk/agent/tools.py` (already shipped on main from RQYyt) — same underlying functions as the CLI verbs, no shell roundtrip, no extra model loads. FastAPI on :8000 satisfies the brief's mandate (`/chat /ingest /sync-status /health`); textual-serve on :8001 ships the Bloomberg-style dashboard with explicit floor / bonus pane sequencing per D6. The v6 Pi-extension experiment archives because once we commit to Textual + textual-serve for the dual TUI/web story, *we don't need Node at all.*

---

## 3. Architecture (target state for v7)

```
                          ┌──────────────────────────────────────────────────┐
                          │   ONE engine per deployment, ONE chat loop,      │
                          │   TWO surfaces, in-process tools                 │
                          ├──────────────────────────────────────────────────┤
   Lite surface           │   Studio TUI (Textual)                           │
   pipx install klerk     │   ┌─ FLOOR panes ────────────┬─ BONUS panes ──┐  │
   klerk chat             │   │ Files │ Chat │ Activity  │ Eval │ KG     │  │
   (~600MB-1.5GB RAM)     │   │       │      │ Status    │      │ Spark  │  │
                          │   │       │      │ Traces    │      │        │  │
                          │   └───────┴──────┴───────────┴──────┴────────┘  │
                          │                                                  │
   Full surface           │   Served via textual-serve at :8001              │
   docker compose up      │   (browser xterm.js wrapper; Textual app runs    │
                          │    server-side as a Python process with the     │
                          │    same in-process engine access as the terminal │
                          │    TUI — NO HTTP shim, NO /internal/* [D2])      │
                          │                                                  │
                          │   FastAPI on :8000                               │
                          │   • /chat (SSE) — brief mandate                  │
                          │   • /ingest /sync-status /health — brief mandate │
                          │   • /memory/* — BONUS [D3], only if Phase B slack│
                          └────────────────────────┬─────────────────────────┘
                                                   │
       ┌───────────────────────────────────────────┴──────────────────────────┐
       │   AGENT LAYER — Hermes-style react loop                              │
       │   (src/klerk/agent/orchestrator.py — DONE on main @ 740cddd)         │
       │   • LangGraph create_react_agent + 6 in-process tools                │
       │   • sliding-window compaction (SessionStore — DONE)                  │
       │   • SOUL.md + MEMORY.md + LanceDB long-term recall (NEW Phase A.2)   │
       │   • Pre-seeds search_hybrid every turn (no-tool fallback)            │
       └───────────────────────────────┬──────────────────────────────────────┘
                                       │ Python imports — in-process [D1]
       ┌───────────────────────────────┴──────────────────────────────────────┐
       │   CORE — shared by orchestrator AND CLI verbs                        │
       │   src/klerk/{rag, agent, drive, orchestrate, memory, ...}            │
       │   Each verb has a function entry point + a typer CLI wrapper.        │
       │   The orchestrator imports the function directly (in-process).       │
       │   The CLI verb wraps it with Midday `--agent --json` mode.           │
       └───────────────────────────────┬──────────────────────────────────────┘
                                       │
       ┌───────────────────────────────┴──────────────────────────────────────┐
       │   CLI verbs — Midday `--agent --json` dual-mode (EXTERNAL contract)  │
       │   For: Claude Code, cron, recruiters' manual shell, future TS rewrite│
       │   NOT for the orchestrator (which calls core directly via tools.py). │
       │                                                                      │
       │   • klerk chat                — opens the TUI                        │
       │   • klerk search hybrid       — single-shot retrieval                │
       │   • klerk extract-actions     — Brief Option B                       │
       │   • klerk contradict scan     — Brief Option C ★ (core)              │
       │   • klerk escalate draft      — Brief Option A                       │
       │   • klerk write               — beyond brief (7-stage doc-writer)    │
       │   • klerk kg extract          — beyond brief                         │
       │   • klerk drive sync/upload   — brief mandate (incremental sync)     │
       │   • klerk eval run            — 20-Q rubric + RAGAS                  │
       │   • klerk memory recall/save  — Hermes trio CLI                      │
       │                                                                      │
       │   APScheduler `drift_runner`  — background, writes drift-events.jsonl│
       └──────────────────────────────────────────────────────────────────────┘

                            Storage layer
                ┌──────────────────────────────────────────┐
                │ LanceDB hybrid (vector + Tantivy BM25)   │
                │   • doc chunks (existing on main)        │
                │   • KG entities + relations (existing)   │
                │   • memory_v1 (NEW Phase A.2)            │
                │ .klerk/sessions/*.jsonl (per-session)    │
                │ XDG/klerk/memory/SOUL.md, MEMORY.md (NEW)│
                │ .klerk/drift-events.jsonl                │
                │ .phoenix/spans.db (trace observability)  │
                └──────────────────────────────────────────┘

                       Embedding backend (pluggable)
                ┌──────────────────────────────────────────┐
                │ LOCAL: BGE-M3 + ColBERT head (FULL mode) │
                │ REMOTE: OpenAI-compat embed endpoint     │
                │         (LITE / user's own self-hosted)  │
                │ Switch: KLERK_EMBED_BACKEND env var      │
                │ Docker compose runs LOCAL for grading    │
                │ (self-hosted BGE-M3 is unambiguous);     │
                │ remote is the constrained-device option. │
                └──────────────────────────────────────────┘
```

**Key architectural choices** (post-D1 / D2 corrections):

1. **No Node, no Pi, no Flue, no TS in v7.** Textual + textual-serve gives terminal-TUI + browser-TUI from one Python codebase. `experimental/pi-extension/` + `experimental/ts-shell/` archive to `docs/explorations/ts-archive/`. Phase C omitted entirely (see §5).

2. **In-process tools, CLI is the external contract.** [D1] The orchestrator's 6 tools (`search_hybrid`, `extract_actions`, `draft_doc`, `scan_conflicts`, `kg_extract`, `drive_sync`) in `src/klerk/agent/tools.py` call core Python modules directly — no `subprocess`, no model reload, hot path stays warm. The Midday `--agent --json` decorator on CLI verbs is for **external** callers (Claude Code, cron, manual shell) who don't have Python import access. CLI verbs and in-process tools call the **same** underlying core entry-point functions.

3. **One engine per deployment.** [D1] **Lite**: `klerk chat` instantiates engine + orchestrator in the Textual process. **Full**: FastAPI on :8000 owns the engine; the textual-serve process on :8001 runs the same Textual app in-process — it's a Python process that streams the rendered terminal over websocket, not a browser app. No second model load.

4. **No `/internal/*` HTTP surface.** [D2] textual-serve doesn't subprocess-spawn the Textual app per visit; it runs the app as a server-side Python process and streams the terminal to xterm.js over websocket. The served Studio has the same in-process engine access as the terminal TUI — **no HTTP shim required**. The earlier `/internal/*` rationale (in the v6 / Stack-D plan) misread textual-serve's architecture; corrected here. HTTP surface = the brief's four endpoints + the optional `/memory/*` bonus.

5. **PydanticAI for fixed-process subagents; LangGraph for multi-step workflows.** Both retained as-is from RQYyt. `action_items` / `kg_extract` / `contradiction.judge_pair` = PydanticAI typed one-shots (DONE on main). `doc_writer` 7-stage fan-out + `scan_conflicts` 4-node = LangGraph state graphs (DONE on main). Reframing only: scan_conflicts is the Brief-Option-C **core**; doc_writer is **beyond brief** [D4].

6. **Brief floor preserved.** FastAPI + Docker + four endpoints + 20-Q eval + incremental Drive sync + 30-doc corpus = all brief mandates intact. The dashboard / memory trio / dual-surface stuff is differentiation polish layered on top.

**Brief options coverage** [D5]:

| Brief option | Implementation | Status |
|--------------|----------------|--------|
| A — Escalation Drafter | `src/klerk/agent/` escalation path + new `klerk escalate draft` verb (Phase A.1) | Plumbing exists on main; CLI verb is new |
| B — Action Item Extractor | `src/klerk/agent/action_items.py` (PydanticAI, on main) + new `klerk extract-actions` verb (Phase A.1) | Core done on main; CLI verb is new |
| C — Conflict Reporter ★ | `src/klerk/orchestrate/` 4-node LangGraph + `klerk contradict scan` verb (on main) | Done; this is our brief-aligned demo flagship |
| Beyond brief | KG extraction (`agent/kg_extract.py`), drift monitor (`scheduled/drift_runner.py`), doc_writer 7-stage LangGraph (`agent/doc_writer_graph.py`) | All done on main; **labeled bonus** in README + EVAL self-assessment so the grader doesn't fault us for off-target focus |

---

## 4. Immediate ground truth (post-merge)

**Done before this plan was committed (Phase A.0 — partial)**:
- ✓ Merge of `claude/handoff-embed-backend-resume-RQYyt` into `main` via merge commit `740cddd`. Both `main` and `claude/agent-framework-planning-jJqQj` at `740cddd`. Pushed.
- ✓ This v7 plan committed at `.planning/v7-plan.md` (force-add since `.planning/` is gitignored — matches RQYyt convention).
- ✓ v6 plan + Stack-D migration doc archived to `.planning/archive/`.
- ✓ HANDOFF.md §13 updated with v7 summary + resume commands.

**Now on main (from RQYyt + the prior docs-on-main lineage joined by merge commit `740cddd`)**:
- LangGraph `/chat` orchestrator with 6 **in-process** tools — D1-compliant by construction.
- SessionStore + sliding-window compaction (short-term memory) at `src/klerk/api/session.py`.
- doc_writer 7-stage LangGraph (`klerk write`) at `src/klerk/agent/doc_writer_graph.py`.
- PydanticAI migration for action_items / kg_extract / contradiction.judge_pair via `src/klerk/agent/pai.py`.
- Remote embed backend + RRF-only rerank fallback in `src/klerk/rag/embed.py` + `rerank.py`.
- Drive read + write (upload) — `klerk drive upload` with `--dry-run`.
- 17 test files / 2,871 LOC tests.

**Still missing for v7**:
- SOUL.md + MEMORY.md + LanceDB `memory_v1` long-term memory trio (Phase A.2)
- Bloomberg-style Studio dashboard (floor + bonus panes per D6, Phase A.3)
- textual-serve wiring (`klerk studio --serve`, Phase A.3)
- Midday `--agent --json` decorator on CLI verbs (D1: **external-only** contract, Phase A.1)
- New CLI verbs: `klerk escalate draft` (Option A) + `klerk extract-actions` (Option B) (Phase A.1)
- Splash + cyberpunk-dark theme (Phase A.3)
- Archive of `experimental/pi-extension/` + `experimental/ts-shell/` → `docs/explorations/ts-archive/` (Phase A.4)
- `pyproject.toml` extras (`lite/server/local/full`) (Phase A.5)
- README rewrite (dual-surface + A/B/C ★ + beyond-brief table) (Phase B.3)
- EVAL.md filled with actual numbers (Phase B.2)

---

## 5. Phased plan with parallel Opus session task split

Deadline confirmed: **31 May 2026 morning Jakarta**. ~5h tonight (Phase A) + ~5h tomorrow morning (Phase B). 4 parallel Opus 4.8 sessions = ~15-20 agent-hours per phase.

### Phase A — Tonight (~5h wall)

**A.0 — Coordinator setup (S0)**
- ✓ Merge RQYyt → main + planning branch at commit `740cddd`
- ✓ Apply D1-D6 deltas to this plan
- ✓ Archive `.planning/v6-plan.md` + `stack-d-migration.md` → `.planning/archive/`
- ✓ Commit `.planning/v7-plan.md` (force-add)
- ✓ HANDOFF.md §13 entry
- TODO: spawn S1-S5 worktrees / sessions
- TODO: open an atomic-commit tracker

**A.1 — Midday CLI verbs (S1, ~2h parallel)**
- `src/klerk/cli/_agent_flag.py` (~50 LOC): `with_agent_mode` decorator. On `--agent`: disable Rich spinners, suppress prompts, route human-readable text to stderr, write exactly one JSON object to stdout, propagate non-zero exit on error.
- Apply decorator to verbs: `search hybrid`, `write`, `contradict scan`, `drive sync`, `drive upload`, `kg extract`, `index build`, `eval run`, `ask`, `memory recall/save/show-soul/edit-soul` (S2 ships memory verbs; S1 applies the decorator).
- NEW verbs:
  - `klerk extract-actions` (~30 LOC) — wraps `agent.action_items.extract()` (PydanticAI, on main). **Brief Option B**.
  - `klerk escalate draft` (~50 LOC) — wraps the escalation path. **Brief Option A**.
- `tests/test_agent_mode.py` (~120 LOC): per-verb assertions — exit code, JSON-on-stdout, no ANSI on stdout, errors → stderr.
- **D1 framing reminder**: this work is for **external** callers. The orchestrator does NOT use these verbs — it imports core directly via `src/klerk/agent/tools.py` (already on main from RQYyt). CLI verbs and orchestrator tools call the same underlying core functions.

**A.2 — Memory trio (S2, ~2.5h parallel)**
- `src/klerk/memory/__init__.py` (~30 LOC): public API surface.
- `src/klerk/memory/store.py` (~180 LOC): `MemoryStore`
  - Persists `SOUL.md` (system-edited identity sketch, seeded with klerk persona — Indonesian-Japanese SaaS firm context, hybrid English-Bahasa workflows) and `MEMORY.md` (append-only fact log) at `${XDG_DATA_HOME:-~/.local/share}/klerk/memory/`.
  - After every assistant turn: extract 0-3 facts via PydanticAI (`MemoryFact` schema), append to MEMORY.md, embed + insert into LanceDB `memory_v1`.
  - `recall(query, k=4)` → hybrid LanceDB over MEMORY.md fragments (vector + Tantivy BM25, RRF fused).
  - `read_soul()` → SOUL.md verbatim, prefix on every turn.
- `src/klerk/cli/memory_cmd.py` (~80 LOC): `klerk memory recall/save/show-soul/edit-soul`. Midday-compliant via S1's decorator.
- `src/klerk/agent/orchestrator.py` patch (~25 LOC): wrap `create_react_agent` invocation so SOUL.md + `recall(query, k=4)` prefix every turn's system prompt.
- `tests/test_memory.py` (~100 LOC).
- **[D3] `/memory/*` FastAPI routes DROPPED from floor.** CLI verbs + in-process TUI access cover memory operations. If Phase B has slack, S2 may add the routes as labeled bonus (~40 LOC in `src/klerk/api/server.py`). Otherwise skip — no brief penalty.

**A.3 — Studio dashboard (S3, ~4h parallel) — sequenced per D6**

**Floor panes (must ship Phase A; this is the dock-and-ship state)**:
- `src/klerk/studio/theme.py` (~60 LOC): cyberpunk-dark palette (Posting magenta + Dolphie cyan), Textual `Theme` object.
- `src/klerk/studio/splash.py` (~80 LOC): klerk ASCII logo + tools/skills inventory + status footer; auto-dismiss on first input (Pi convention).
- `src/klerk/studio/widgets/files.py` (~120 LOC): Harlequin-pattern `Tree` rooted at corpus + `.klerk/` + `data/output/`.
- `src/klerk/studio/widgets/live_chat.py` (~200 LOC): `Input` + scrollable `MessageLog`. **Lite mode**: instantiates orchestrator in-process. **Full mode**: opens SSE to `/chat`. Tool-call / tool-result events render as collapsible cards inline. Reuses existing chat panel code from `src/klerk/studio/app.py` where possible.
- `src/klerk/studio/widgets/activity.py` (~80 LOC): `DataTable` tailing `.klerk/activity-log.jsonl`.
- `src/klerk/studio/widgets/status_bar.py` (~50 LOC): top bar polling `/health` every 5s — model + Drive sync state + WIB time + ctx tokens.
- `src/klerk/studio/widgets/traces.py` (~50 LOC): Phoenix link button + last-span summary.
- `src/klerk/studio/app.py` (~150 LOC delta): `Grid` composing floor widgets + splash mount + `--serve` flag wiring `textual-serve.Server`; `--lite` chat-only fallback for narrow terminals (<120 cols).

**Bonus panes (build only if floor green + Phase B has slack)**:
- `src/klerk/studio/widgets/eval_panel.py` (~70 LOC): 5-axis + RAGAS row from `.klerk/eval-runs/<latest>.json`.
- `src/klerk/studio/widgets/kg_snapshot.py` (~70 LOC): top-10 entities + counts DataTable.
- `src/klerk/studio/widgets/graph.py` (~90 LOC): 3 stacked Sparklines — latency p95 / tools-per-minute / eval rubric mean.

**Cut order [D6]** if Phase B time pinches: drop **eval panel first** (signal lives in EVAL.md), then **KG** (no brief anchor), then **sparklines** (eye candy).

**A.4 — Docker + archive (S4, ~1.5h parallel)**
- `Dockerfile`: Python-only base (drop Node from the image — no more TS experiments inside the container); add `textual-serve` dep; `ARG KLERK_EMBED_BACKEND=local` for conditional BGE-M3 bake. Embed model stays **local in the compose demo** so the graded `docker compose up` is unambiguous about self-hosting BGE-M3.
- 15-line bash entrypoint script with `tini` PID-1 + `wait -n` running uvicorn :8000 and textual-serve :8001 concurrently. No supervisord / s6-overlay needed.
- `docker-compose.yml`: expose :8001; healthcheck `start_period: 60s` for BGE-M3 cold load.
- README "Three install paths": Docker (graded path) / pipx + remote embed (lite demo) / Dev.
- Move `experimental/pi-extension/` + `experimental/ts-shell/` → `docs/explorations/ts-archive/`. Write `docs/explorations/EXPLORATIONS.md` narrating "v6 detour, learned, didn't ship — v7 chose textual-serve for the same 2nd-surface goal with less code." Honest "we built, learned, didn't ship" arc — matches brief's anti-over-engineering guidance.

**A.5 — pyproject extras + EmbedBackend + XDG (S5, ~1.5h parallel)**
- `pyproject.toml` extras: `lite = []`, `server = ["uvicorn", "fastapi", "textual-serve", ...]`, `local = ["FlagEmbedding", "torch", "transformers"]`, `full = ["klerk[server,local]"]`. Default `pip install klerk` = lite. (LangFlow 8-extras pattern is the precedent.)
- `src/klerk/rag/embed.py`: `EmbedBackend` ABC polish around `LocalBGE` (gated `import FlagEmbedding`, raises actionable error if missing) and `RemoteOpenAICompat` (already on main from RQYyt). Env-driven via `KLERK_EMBED_BACKEND=remote|local|mock`.
- XDG paths everywhere: `${XDG_DATA_HOME:-~/.local/share}/klerk/{sessions,memory,lancedb}` + `${XDG_CONFIG_HOME:-~/.config}/klerk/config.yaml`. Project-local `./.klerk/` remains an override (Aider-style).

### Phase B — Tomorrow morning (~4-5h wall)

**B.1 — Integration smoke (S0 + handoff from A.1-A.5, ~2h wall)**
- Merge S1-S5 branches into the planning branch in topological order (see §6).
- `pytest` all green (143 existing + ~250 new from Phase A = ~400 tests).
- `docker compose up` smoke: open `http://localhost:8001` → Bloomberg floor panes render with cyberpunk theme + splash; chat panel SSE streams; tool-call cards visible; activity panel populates; status bar polls /health; Drive sync state reflected.
- `pipx install -e .` lite smoke in a fresh venv: `KLERK_EMBED_BACKEND=remote KLERK_EMBED_REMOTE_URL=… klerk chat` opens TUI with in-process engine, completes a turn. RAM < 1GB.

**B.2 — Eval + EVAL.md (S6, ~1.5h parallel with B.1)**
- `klerk eval run --rubric` against the 20 Qs.
- Capture screenshots of dashboard + chat.
- Fill EVAL.md with actual numbers + per-category breakdown + honest failure analysis + bias disclosure.

**B.3 — README + HANDOFF v7 (S7, ~1.5h parallel)**
- README rewrite: lead with dual-surface narrative; install matrix (Docker / pipx-lite / Dev); brief-compliance table with A/B/C ★ + beyond-brief split [D5].
- Bloomberg dashboard screenshot.
- Hermes credit fixed (Anthropic "Building Effective Agents" → ReAct loop; Hermes Agent → SOUL.md/MEMORY.md trio + gws-mcp side-car inspiration).
- HANDOFF.md §13 v7 entry — branch state at `740cddd`, decisions, deltas D1-D6 captured (already done; refresh if needed).
- "Beyond brief" subsection in self-assessment listing KG / drift / doc_writer.
- DATA_GENERATION.md sweep — confirm still v5-current; add Drive upload flow note.

**B.4 — Submit (S0, ~30min)**
- Final smoke.
- Push planning branch (main is already at floor since merge `740cddd`).
- Verify Drive folder shared with `ydharmaw@fata-organa.com` Editor.
- Compose submission email — repo URL + Drive folder ID + self-assessment + hardware notes + "connected to Nemotron proxy successfully" line.

### Phase C — OMITTED [D-list, user direction]

The TS+Bun full rewrite (Flue / Mastra / Bun-as-runtime) is **explicitly out of scope** for v7. The v7 architecture is **Phase-C-friendly** (Midday CLI-as-contract means a future TS agent layer can wrap the existing Python substrate via `Bun.spawn` without rewriting core), but **no Phase C work happens for the May 31 submission**. If the user wants to spike Phase C post-submission, a fresh branch `claude/v7-ts-rewrite-experiment` can scaffold a Flue chat loop that delegates to Python CLI verbs — but that's days of work, not minutes.

---

## 6. Parallel Opus session coordination

| Session | Owns (no overlap) | Touches (coordinate) | Phase |
|---------|-------------------|----------------------|-------|
| **S0** | this session — plan, merges, README, HANDOFF, submission, integration | — | A+B |
| **S1** | `cli/_agent_flag.py`, `extract_actions_cmd.py`, `escalate_cmd.py`, edits to every `*_cmd.py` (~13 files), `tests/test_agent_mode.py` | — | A |
| **S2** | `src/klerk/memory/`, `cli/memory_cmd.py`, `tests/test_memory.py` | `agent/orchestrator.py` (+25 LOC prefix block); coordinates via this plan note: "S2 owns the prefix block; S5 does not touch it" | A |
| **S3** | all of `src/klerk/studio/` — **floor panes first**, then bonus per D6 cut order | — | A |
| **S4** | `Dockerfile`, `docker-compose.yml`, supervisor script, `Makefile`, `docs/explorations/` | `pyproject.toml` (textual-serve dep added to `server` extra — coordinate with S5 who owns the extras block) | A |
| **S5** | `pyproject.toml` extras block, `rag/embed.py` ABC polish, XDG helpers, `.env.example` | `pyproject.toml` (S5 sets up extras first; S4 then appends textual-serve to `server`) | A |
| **S6** | `EVAL.md`, runs `klerk eval run` | — | B |
| **S7** | `README.md`, `HANDOFF.md` §13 refresh, `DATA_GENERATION.md` sweep, `docs/architecture.md` v7 diagram | — | B |

Merge order into planning branch: **S5 → S1 → S2 → S3 (floor) → S3 (bonus if shipped) → S4 → S6 → S7**. S0 resolves conflicts.

**Cut signals for S3** [D6]:
- Floor not green by Phase B start → ship floor only (Chat / Files / Activity / Status / Traces).
- Floor green + B.1 hitting friction → cut **eval panel** first, then **KG**, then **sparklines**.
- Floor green + Phase B has slack → build bonus in order: **eval** (highest signal), **KG** (differentiation), **sparklines** (eye candy).

**Quality bar per session**:
- All new code has tests; tests pass before push to S0
- No `experimental/` changes without S0 approval (S4 owns the archive move)
- PydanticAI at typed boundaries (continue the RQYyt pattern)
- Type-hinted Python; mypy clean (project convention)
- Atomic commits with conventional-commit prefixes (`feat`, `fix`, `refactor`, `docs`, `chore`, `test`)

---

## 7. Decision log

### Why in-process tools, not subprocess shell-out [D1]

The Midday `--agent --json` CLI pattern is a contract for **external callers** (Claude Code, cron, recruiters' manual shell sessions). It is **not** how the orchestrator calls its own tools — the orchestrator has direct Python import access to the same core modules. Subprocess-per-tool-call would pay Python startup + import cost on every invocation (and a `torch` model reload if FlagEmbedding is on the import path), which is fatal on the 600MB-1.5GB lite target and wasteful in full mode too. RQYyt's `tools.py` correctly implements the 6 tools as thin wrappers around in-process core functions; v7 keeps and clarifies this. The v6/Stack-D plan's "subprocess boundary = clean separation" framing was wrong — corrected here.

### Why no `/internal/*` HTTP shim [D2]

The earlier rationale ("browser Studio can't subprocess-spawn so /internal/* exists") misread textual-serve's architecture. textual-serve runs the Textual app as a **server-side Python process** and streams the rendered terminal to xterm.js over websocket. The served Studio has the same in-process engine access as the terminal TUI — no HTTP shim required. Dropping `/internal/*` shrinks the API surface to the brief's four mandates + the optional `/memory/*` bonus, removes an entire endpoint family built on a wrong assumption, and saves ~150 LOC of routing + tests.

### Why `/memory/*` is bonus, not floor [D3]

The brief mandates only four endpoints. Direct memory ops are already covered by Midday CLI verbs (`klerk memory recall/save/show-soul/edit-soul`) and by the TUI's in-process engine access. `/memory/*` routes would only matter for an external HTTP client that isn't klerk-aware — out of scope for the May 31 submission. Phase B can add them as labeled bonus if there's slack; otherwise no brief penalty.

### Why doc_writer is reframed as bonus, scan_conflicts is core [D4]

The brief asks for ≥1 of {A Escalation Drafter, B Action Item Extractor, C Conflict Reporter} — all retrieval / QA agentic capabilities. There is **zero brief surface for document generation**. **Conflict Reporter (Option C) maps directly to our 4-node LangGraph `scan_conflicts`** — that's the core ticked box for the brief. The 7-stage adversarial doc_writer is genuinely impressive engineering but answers a question the brief never asked. It stays in the repo (already on main from RQYyt) but README + EVAL + self-assessment label it as "beyond brief" so the grader doesn't fault us for off-target focus.

### Why all three A/B/C [D5]

The corpus naturally supports all three options and the implementations are cheap (action_items + escalation + conflict). Tick all three boxes in the brief-compliance table; this is well within "demonstrating depth" rather than "over-engineering." Honest line in self-assessment: "all three implemented; conflict reporter is the most polished and integrated into both the chat agent and the dashboard."

### Why Studio sequenced behind the floor [D6]

The brief explicitly mentions fancy UI as a non-requirement and warns about over-engineering deductions. A 9-widget Bloomberg-style dashboard is the surface most exposed to that read. Sequencing ensures the brief floor (four endpoints + Drive sync + 30-doc corpus + 20-Q eval + `docker compose up` + the three docs) is green first; the floor panes give the dashboard real signal (Chat shows the agent works; Files shows the corpus; Activity shows tools running; Status bar shows health; Traces shows observability); bonus panes are nice-to-have with an explicit cut order. If everything ships, the dashboard is the wanted flex. If time pinches, we still have a solid floor + a 5-pane studio that's better than the brief's Streamlit suggestion (which we replace with textual-serve served Textual TUI).

### Why no Node / no Pi / no Flue / no TS in v7

- **Pi**: confirmed can't do horizontal multi-pane dashboards (vertical-stack TUI only). Pi-extension was the v6 detour that doesn't have a home in v7's architecture.
- **Flue**: 4-6 week rewrite; kills the Python substrate (PydanticAI, LangGraph subgraphs, native LanceDB hybrid search with Tantivy BM25, ColBERT head, Docling parser, FlagEmbedding). Phase C → omitted.
- **TS+Bun full rewrite**: 6-9 weeks; `@lancedb/lancedb` on Bun is REST-only (NAPI-RS needs V8); no BM25/FTS in JS as of May 2026; no ColBERT in TS. Bun-on-proot-Debian works fine but ecosystem gaps are non-negotiable.

### Why archive `experimental/pi-extension/` + `experimental/ts-shell/`

- v7 ships **one substrate (Python) + two surfaces (Textual terminal + Textual served via textual-serve)**. The Pi-extension was a v6 detour that doesn't have a home in v7. Keeping it in `experimental/` would imply ongoing investment.
- Move to `docs/explorations/ts-archive/` with `EXPLORATIONS.md` narrating "v6 detour, learned, didn't ship — v7 chose textual-serve for the same 2nd-surface goal with less code; the Phase C TS+Bun rewrite is a separate exploration left as a future direction, not in v7."
- Honest "explored, learned, didn't ship" arc — matches the brief's anti-over-engineering guidance.

### Why Hermes trio (SOUL.md + MEMORY.md + LanceDB) instead of Honcho/Mem0/Letta

- **Honcho**: AGPL + Postgres + Redis + Deriver worker. Way too heavy for a 25-doc corpus + a take-home submission.
- **Mem0**: Apache + lighter but still adds Qdrant or sqlite + a second eval surface. Skip.
- **Letta**: extra service surface and a markedly different agent model. Skip.
- **Hermes trio**: file convention (SOUL.md + MEMORY.md) + one LanceDB table (`memory_v1`). Already have LanceDB in the stack. ~180 LOC total. Demo signal: "we read the Hermes room (Nous Research) without taking Hermes' weight."

### Why FastAPI stays

- Brief mandates `/chat /ingest /sync-status /health` over FastAPI. Pass/fail item.
- The RQYyt merge already wires the agent loop through `/chat` (LangGraph orchestrator + 6 in-process tools + SessionStore). Removing FastAPI would force brief renegotiation with zero upside.
- FastAPI is also where `/memory/*` lives if we ship the optional bonus (D3).

### Why parallel Opus 4.8 sessions

- User leverage: 4 parallel sessions ≈ 15-20 agent-hours per phase, vs. ~14h serial.
- Non-overlapping file sets per §6 eliminate merge thrash.
- S0 coordinator is the single integration point; other sessions never read each other's WIP — they read S0's merged planning branch.

### Why ship May 31 from main (already at `740cddd`)

- `main` with the RQYyt merge already satisfies the **brief floor**: agentic `/chat`, multi-turn memory base, retrieval / QA capabilities A/B/C, 20-Q eval scaffold, `docker compose up`, three required docs (README + EVAL + DATA_GENERATION).
- v7 Phase A polish (memory trio + Bloomberg dashboard + Midday verbs + dual-surface docs) layers differentiation on top.
- Phase A overrun risk is absorbed by the fact that main is already at floor — if any Phase A piece misses, we ship from `740cddd` with the polish that did land.

---

## 8. Critical files to modify

### New files (Phase A)

```
src/klerk/cli/_agent_flag.py                 ~50  Midday --agent decorator [D1] (S1)
src/klerk/cli/extract_actions_cmd.py         ~30  Brief Option B CLI verb (S1)
src/klerk/cli/escalate_cmd.py                ~50  Brief Option A CLI verb (S1)
src/klerk/cli/memory_cmd.py                  ~80  Memory CLI ops (S2)
src/klerk/memory/__init__.py                 ~30  public API (S2)
src/klerk/memory/store.py                    ~180 SOUL.md/MEMORY.md/LanceDB store (S2)
src/klerk/studio/theme.py                    ~60  cyberpunk-dark Textual theme (S3)
src/klerk/studio/splash.py                   ~80  klerk ASCII splash (S3)
src/klerk/studio/widgets/files.py            ~120 FLOOR — Harlequin Tree (S3)
src/klerk/studio/widgets/live_chat.py        ~200 FLOOR — chat panel + tool-call cards (S3)
src/klerk/studio/widgets/activity.py         ~80  FLOOR — JSONL tail DataTable (S3)
src/klerk/studio/widgets/status_bar.py       ~50  FLOOR — top bar polling /health (S3)
src/klerk/studio/widgets/traces.py           ~50  FLOOR — Phoenix link (S3)
src/klerk/studio/widgets/eval_panel.py       ~70  BONUS — 5-axis + RAGAS [D6] (S3)
src/klerk/studio/widgets/kg_snapshot.py      ~70  BONUS — entities DataTable [D6] (S3)
src/klerk/studio/widgets/graph.py            ~90  BONUS — Sparklines [D6] (S3)
docs/explorations/EXPLORATIONS.md            ~80  archive narrative (S4)
docs/explorations/ts-archive/README.md       ~40  pointer to git history (S4)
tests/test_agent_mode.py                     ~120 per-verb JSON+exit checks (S1)
tests/test_memory.py                         ~100 store + recall + soul (S2)
```

### Modified files (Phase A)

```
src/klerk/agent/orchestrator.py              ~+25 SOUL+recall prefix on every turn (S2)
src/klerk/cli/*_cmd.py                       ~+5  per-verb @with_agent_mode (S1, ~13 files)
src/klerk/rag/embed.py                       ~+30 EmbedBackend ABC polish (S5)
src/klerk/studio/app.py                      ~+150 Grid layout, splash, --serve, theme (S3)
pyproject.toml                               ~+25 extras (lite/server/local/full) (S5+S4)
Dockerfile                                   ~+30 ARG conditional BGE-M3, textual-serve, tini (S4)
docker-compose.yml                           ~+15 expose :8001, healthcheck delta (S4)
Makefile                                     ~+10 demo-lite target (S4)
README.md                                    ~+200 dual-surface + A/B/C ★ + beyond-brief (S7)
HANDOFF.md                                   ~+150 §13 v7 + deltas D1-D6 (S0/S7)
.env.example                                 ~+8 KLERK_EMBED_REMOTE_*, KLERK_TUI_THEME (S5)
docs/architecture.md                         ~+50 v7 diagram (S7)
EVAL.md                                      ~+100 actual eval results (S6)
```

### Optional Phase B (bonus, [D3])

```
src/klerk/api/server.py                      ~+40 /memory/* routes (S2 if Phase B slack)
```

### Files moved

```
experimental/pi-extension/ → docs/explorations/ts-archive/pi-extension/  (S4)
experimental/ts-shell/     → docs/explorations/ts-archive/ts-shell/      (S4)
.planning/v6-plan.md       → .planning/archive/v6-plan.md                (S0, DONE)
.planning/stack-d-migration.md → .planning/archive/stack-d-migration.md  (S0, DONE)
```

### Files reused as-is (DONE on main via RQYyt merge `740cddd`)

- `src/klerk/agent/orchestrator.py` — Hermes-style react loop (S2 patches the prefix block only)
- `src/klerk/agent/tools.py` — 6 **in-process** tool definitions [D1]
- `src/klerk/api/session.py` — SessionStore + sliding-window
- `src/klerk/agent/doc_writer_graph.py` — 7-stage LangGraph (reframed as bonus per [D4])
- `src/klerk/orchestrate/` — 4-node conflict LangGraph (★ Brief Option C core)
- `src/klerk/agent/pai.py` — PydanticAI helper for typed one-shots
- `src/klerk/rag/embed.py` — remote backend already plumbed (S5 polishes the ABC)

---

## 9. Verification

End-to-end test plan, executed in Phase B.1:

1. `pytest` green: 143 existing + ~250 new from Phase A = ~400 tests.
2. **Midday compliance** [D1]: for each verb in §A.1, `klerk <verb> --agent --json …` returns exactly one JSON object on stdout, exit 0, no ANSI on stdout; errors go to stderr.
3. **Memory roundtrip**: `klerk memory save "Atlas escalates to PMO at severity≥3"`; `klerk memory recall "escalation"` returns the fact with score > 0.5; next chat turn shows MEMORY.md prefix in the constructed system prompt.
4. **`/chat` agentic loop, in-process tools** [D1]: `curl -N -X POST :8000/chat -d '{"query": "What does the SOP say about WFH?"}'` → SSE: `tool_call(search_hybrid)` → `tool_result` → `token` stream → `citations` → `done`. Tools resolve **in-process** — verify via process tree that no subprocess is spawned per tool call.
5. **Brief Q coverage**:
   - **Trick Q** ("Berapa harga saham bulan depan?") → `confidence: 0.0` + escalation drafted
   - **Conflict Q** (WFH 2023 vs 2025) → `scan_conflicts` LangGraph runs, structured side-by-side report streamed
   - **Bahasa Q** ("Apa kebijakan cuti melahirkan?") → answer in Bahasa with citations
6. **Lite mode**: in a fresh venv, `pipx install -e .[lite]`; `KLERK_EMBED_BACKEND=remote KLERK_EMBED_REMOTE_URL=<self-hosted> klerk chat`. TUI opens with floor panes. One turn completes. RAM < 1GB.
7. **Full mode**: `docker compose up --build`. Open `http://localhost:8001` → Bloomberg floor panes render with cyberpunk theme; splash auto-dismisses on first input; chat panel streams; activity panel updates; status bar polls /health; Drive sync state reflected. Floor green. Bonus panes optional per [D6].
8. **textual-serve sanity** [D2]: open dashboard in a second browser tab; both tabs work without cross-talk (textual-serve subprocess isolation).
9. `docker compose down` → no orphan processes; volumes intact.
10. **Eval**: `klerk eval run --rubric` against 20 Qs; rubric mean ≥3.5/5 on factual, ≥3.0/5 overall; EVAL.md committed with the numbers + per-category breakdown + honest failure analysis.

---

## 10. Open scoping questions (defer to execution)

1. **Splash auto-dismiss timing**: 1.5s vs first-keypress (default first-keypress, Pi convention).
2. **textual-serve auth**: localhost only tonight; Cloudflare Access doc for future Fly.io deploy.
3. **KG panel refresh trigger**: live on drive sync vs 30s cache (default cached IF the KG panel ships at all per [D6] cut).
4. **Phoenix trace pane**: link-out via `webbrowser.open` (default) vs embedded sqlite render.
5. **Archive `package.json` lockfiles**: keep (git history is the record) vs strip (default keep).
6. **Lite-mode invocation**: `pipx run klerk-cli` vs `pipx install klerk` then `klerk chat` (default install for persistent demo).
7. **Optional `klerk drift monitor --live`** for the Activity pane (S3 decides if floor includes it; default no, drift events are tailed from JSONL).
8. **`klerk escalate draft` output shape**: structured email body (default) vs sendable mail (sender wiring is out of scope).
9. **`/memory/*` routes**: build in Phase B if slack vs skip (default skip per [D3]).
10. **`.planning/` archive policy**: archived plans live on the planning branch only (default), or also propagate to main (no — main's archive lives in git history via the merge commit and via `.planning/archive/` on the planning branch).
