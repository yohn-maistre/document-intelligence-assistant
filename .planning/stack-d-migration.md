# Stack D migration plan — Pi 2nd surface + Bloomberg-terminal studio

**Date**: 2026-05-30
**State**: Clusters 1-4 done on `main` (`ffb8ae9` + the other session's cluster 2-4 commits). Cluster 5 partially started, stopped on pivot.
**Branch convention**: Stack D work continues on the other session's branch; merges to `main` when each phase ships.

---

## Why pivot (and why nothing gets thrown away)

The four-agent sweep (Pi capabilities · Midday pattern · textual-serve · 2026 dashboard survey) converged on a different shape than Stack C had:

1. **Pi philosophically rejects deterministic graphs.** Mario's "No MCP / No plans / No todos" design omits subagents and state machines from core. Our 7-stage adversarial doc-writer and 4-node conflict scanner are exactly what Pi refuses to host. → **LangGraph subagents stay in Python.**

2. **Pi is best used as a flat tool loop that calls outside.** RPC mode (`pi --mode rpc`) is the clean seam; tools can shell out to anything. → **Pi as a 2nd surface, not a host.**

3. **Midday's pattern is the contract**: dual-mode CLI (`--agent` flag → JSON, no spinners, no prompts, env-var auth). Any agent shells out — no harness wraps anything. → **klerk CLI verbs become the tool contract for every surface (Pi, FastAPI orchestrator, Claude Code, cron).**

4. **Cluster 4 is not orphaned by this**: the LangGraph orchestrator IS the brief's `/chat` surface. Pi is the developer-facing parallel surface. Both call the same CLI verbs. **Two surfaces, one tool layer** — exactly the Hermes pattern we already credit in `README.md:159` and `docs/architecture.md:3`.

5. **Studio dashboard stays Textual**, gets the 5+ panel Bloomberg-terminal treatment (Dolphie / Posting / Harlequin reference DNA) instead of a side-rail. textual-serve handles browser embed; reference projects (Harlequin, Posting, Dolphie, Elia) prove the pattern scales.

**Net**: clusters 1-4 preserved. Cluster 5 plan replaced. Cluster 6 plan rewritten (CLI shellout, not HTTP `/internal/*`).

---

## Architecture

```
TWO SURFACES, ONE TOOL LAYER, ONE SUBAGENT POOL

┌──────────────────────────────┐    ┌──────────────────────────────┐
│ klerk chat (Pi 0.78+)        │    │ FastAPI /chat (SSE)          │
│ • Pi flat tool loop          │    │ • LangGraph create_react_    │
│ • Pi's own session memory    │    │   agent (cluster 4)          │
│ • Pi-extension defines tools │    │ • SessionStore + sliding-    │
│   that shell out             │    │   window (cluster 4)         │
│ • Nemotron via OpenAI-compat │    │ • Nemotron via LiteLLM       │
│ ─────────────────────────────┤    ├──────────────────────────────┤
│ DEVELOPER SURFACE            │    │ BRIEF-MANDATED SURFACE       │
└──────────────┬───────────────┘    └──────────────┬───────────────┘
               │                                   │
               └───────────────┬───────────────────┘
                               ▼
       ┌─────────────────────────────────────────────────┐
       │ TOOL LAYER — klerk CLI verbs (Midday pattern)   │
       │   klerk search hybrid    --agent --json ...     │
       │   klerk write            --agent --json ...     │
       │   klerk contradict scan  --agent --json ...     │
       │   klerk extract-actions  --agent --json ... NEW │
       │   klerk drive sync       --agent --json ...     │
       │   klerk kg extract       --agent --json ...     │
       │   klerk index build      --agent --json ...     │
       └────────────────────────┬────────────────────────┘
                                ▼
       ┌─────────────────────────────────────────────────┐
       │ SUBAGENT LAYER (Python)                         │
       │   LangGraph doc_writer (7-stage adversarial)    │
       │   LangGraph conflict scanner (4-node)           │
       │   PydanticAI action_items, kg_extract,          │
       │                contradiction.judge_pair         │
       │   LiteLLM hybrid search (LanceDB + BGE-M3)      │
       └─────────────────────────────────────────────────┘

Observability:
       APScheduler drift_runner ─→ .klerk/drift.jsonl
       Phoenix spans            ─→ .phoenix/ (local SQLite)
       Activity events          ─→ .klerk/activity-log.jsonl
                                    (consumed by Studio via WS bus,
                                     disler pattern)
```

---

## Studio dashboard layout

**Reference DNA**: Dolphie (multi-panel live metrics, blue palette), Posting (purple/magenta accent, clean type), Harlequin (file-explorer tree + tabbed editor + results table).

**Layout** (default ~120×40 terminal; gracefully reflows narrower):

```
┌─ klerk studio · main · Nemotron OK · Drive 2m · 28 docs · session #4 ────────┐
├──────────────┬───────────────────────────────┬───────────────────────────────┤
│ Files        │ Live Chat                     │ Activity                      │
│ corpus/      │                               │ 14:23 search_hybrid     847ms │
│ ▸ hr/        │ > How does Atlas escalate?    │ 14:23   12 chunks returned    │
│ ▸ sop/       │ < (streaming with [1][2]      │ 14:24 LLM stream started      │
│ ▸ minutes/   │    citations…)                │ 14:24   1247 tok @ 142 t/s    │
│ ▸ faqs/      │                               │ 14:24 draft_doc        2.1s   │
│ .klerk/      │                               │ ...                           │
│ ▸ sessions/  │ ⌽ ____________________________│                               │
│ ▸ kg/        ├───────────────────────────────┼───────────────────────────────┤
│ ▸ eval-runs/ │ Graph (last 60s)              │ KG snapshot                   │
│ .lancedb/    │ latency  ▁▂▃▆█▇▆▄             │ Entities: 142  Relations: 387 │
│ data/output/ │ tools/m  ▂▃▅▇█▆▄              │ Top:                          │
│              │ eval     ▆▆▇▇█▇▇              │  · Project Atlas    24 docs   │
│              │                               │  · PT Fata Organa   18        │
│              │                               │  · Yanitra Dharma   15        │
├──────────────┴───────────────────────────────┴───────────────────────────────┤
│ Eval & Traces  ┌─ Eval ─┬─ Traces ─┬─ Both ─┐                                │
│                                                                              │
│ 5-axis rubric mean 4.1/5 · run 2026-05-30 13:50 · 20 Qs                      │
│ Faithfulness 4.3  Relevance 4.0  Completeness 3.9  Coherence 4.2  Cite 4.0   │
│                                                                              │
│ Phoenix → open browser  ·  last span: chat#4 1.2s 12 chunks 2 tools          │
├──────────────────────────────────────────────────────────────────────────────┤
│ ?:help  q:quit  n:new-chat  /:cmd  f:files  g:graph  k:kg  t:traces  e:eval  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Panels**:

| ID | Panel | Source | Refresh | LOC est |
|---|---|---|---|---|
| `files` | File explorer (Harlequin tree) | walk `corpus/`, `.klerk/`, `.lancedb/`, `data/output/` | on-startup + watch | ~120 |
| `chat` | Live chat (streaming SSE) | `/chat` (LangGraph) via httpx-sse | per token | ~200 |
| `activity` | Tool-call timeline | `.klerk/activity-log.jsonl` + WS bus | tail follow | ~80 |
| `graph` | Sparkline metrics (latency, tool/min, eval mean) | rolling 60s window from activity bus | 1s tick | ~100 |
| `kg` | Entities/relations snapshot | `.klerk/kg/snapshot.json` | on drive-sync event | ~80 |
| `eval` | RAGAS + 5-axis rubric scores | `.klerk/eval-runs/<latest>.json` | manual + on eval-end | ~80 |
| `traces` | Phoenix link + last-span summary | `.phoenix/spans.db` (read-only sqlite) | 5s tick | ~60 |
| `status` | Top bar (model, drive, docs, session) | `/health` poll | 5s tick | ~40 |
| `footer` | Keybindings | static | — | ~20 |

**Palette** (Textual CSS, muted cyberpunk dark):

```css
$background:  #0d0d1a;   /* deepest — root */
$panel:       #161628;   /* panel surfaces */
$boost:       #1f1f33;   /* hover / selected row */
$accent:      #ff5fd7;   /* Posting magenta — selections, headers */
$primary:     #00d7d7;   /* Dolphie cyan — primary text accent */
$success:     #5fd75f;   /* OK / synced / passed */
$warning:     #d7d75f;   /* in-progress / partial */
$error:       #d75f5f;   /* failed / timeout */
$text:        #d0d0d0;   /* primary text */
$text-muted:  #707080;   /* secondary text, dim labels */
$border:      #3a3a5a;   /* panel borders, muted */
```

Title bar gets a gradient stripe (magenta→cyan) for the cyberpunk glow without the noise.

---

## Migration phases

Estimates given the current state (clusters 1-4 done, 143 tests green on main).

### Phase 0 — Status reconcile (~30min)

- `git fetch && git log origin/main` → confirm cluster 4 commits (LangGraph orchestrator, 6 tools, /chat rewire) landed
- `uv sync && pytest` → green baseline
- Read what the other session shipped in cluster 4 — confirm SSE event types match v6 plan (`session`, `tool_call`, `tool_result`, `token`, `citations`, `done`)
- If cluster 4 diverged from v6 plan, log the deltas; do NOT change cluster 4 code now

### Phase 1 — Midday-pattern CLI verbs (~2h)

The contract that makes everything else clean.

- `src/klerk/cli/_agent_flag.py` (NEW ~40 LOC): `@with_agent_mode` decorator. When `--agent` is set: disable Rich spinners, disable colors, suppress confirmation prompts, route human-readable output through `sys.stderr`, route the *one structured result* through `sys.stdout` as a single JSON line. Same env-var pattern as Midday (`KLERK_AGENT_MODE=1`).
- Apply to verbs: `propose` (now `write`), `search hybrid`, `search bm25`, `search vector`, `contradict scan`, `drive sync`, `kg extract`, `index build`, `index stats`, `eval run`, `anomaly scan`, `faq build`, `ask`
- **NEW verb**: `klerk extract-actions --src <file> --agent --json` — wraps the PydanticAI action_items one-shot. ~30min.
- `tests/test_agent_mode.py` (NEW ~80 LOC): for each verb, assert `--agent` emits exactly one JSON object to stdout, no ANSI escapes, non-zero exit on error.

### Phase 2 — Pi 2nd surface (~3h)

Replaces the old cluster 6 (HTTP `/internal/*` path). Pi tools shell out to CLI verbs.

- `experimental/pi-extension/package.json`: bump peer dep to `@earendil-works/pi-coding-agent@^0.78`
- `experimental/pi-extension/src/tools/` — rewrite each tool's `execute()` to spawn `klerk <verb> --agent --json ...` via `node:child_process.execFile`. Parse stdout JSON. Stream stderr to Pi's `onUpdate` callback for in-tool progress visibility.
- Drop any `/internal/*` HTTP references in the system prompt; rewrite the system prompt to enumerate CLI verbs as tools.
- `experimental/ts-shell/` → `cli/` (top-level repo move). `pnpm install`; `pnpm build` smoke test.
- `cli/package.json`: name `@yohnmaistre/klerk-cli`, version `0.1.0`, `bin: { "klerk-chat": "./bin/chat.js" }`. Publish-ready locally; don't actually publish tonight.
- `cli/README.md` — install + usage walkthrough.

### Phase 3 — Studio dashboard (~6h, replaces old cluster 5)

The Bloomberg-terminal Textual layout per the screenshots and palette above.

- `src/klerk/studio/theme.py` (NEW ~50 LOC): Textual `Theme` object with the palette.
- `src/klerk/studio/app.py` — replace the v5 single-panel layout with a `Grid` composing the nine widgets. Reactive layout: 80-col + falls back to tabs.
- `src/klerk/studio/widgets/` (NEW):
  - `files.py` — Harlequin-style `Tree`, walks `corpus/` + `.klerk/` + `.lancedb/` + `data/output/`. Click-to-open opens previewer in the chat pane.
  - `live_chat.py` — `MessageLog` + `Input`. Streams `/chat` SSE; renders `tool_call` / `tool_result` events as collapsible cards inline. Persists `session_id` in panel state.
  - `activity.py` — Reactive `DataTable`; subscribes to WS event bus (see below).
  - `graph.py` — Three `Sparkline` widgets (latency / tool-rate / eval-mean) stacked. 60s rolling window.
  - `kg_snapshot.py` — `DataTable` of top entities + counts; refreshes on `drive-sync-end` event.
  - `eval_panel.py` — Read `.klerk/eval-runs/<latest>.json`; render 5-axis row + RAGAS row.
  - `traces.py` — Read-only sqlite on `.phoenix/spans.db`; show last span summary + button: `[Open Phoenix in browser]` (uses `webbrowser.open()` per dashboard-survey recommendation).
  - `status_bar.py` — top bar; polls `/health` every 5s.
- **WS event bus** (disler pattern): `src/klerk/api/events.py` (NEW ~80 LOC). FastAPI gains `/events/ws` WebSocket. Activity panel subscribes. The orchestrator's existing event emission (cluster 4) writes to the bus AND to `.klerk/activity-log.jsonl` (durability). Pi (when in use) also emits to the bus via a small HTTP POST in each tool's `execute()`.
- `klerk studio` CLI flags: `--lite` (chat-only fallback), `--serve` (textual-serve), `--theme cyberpunk-dark` (default), `--theme classic`.

### Phase 4 — textual-serve + deployment (~2h, can defer)

- Add `textual-serve>=1.1` to `pyproject.toml`.
- `klerk studio --serve` → `Server("klerk studio").serve()`.
- `Makefile`: `demo-lite` target (set `KLERK_EMBED_BACKEND=remote`, launch `--serve`).
- README — document the Fly.io + Cloudflare Access pattern for a public reviewer URL. Don't actually deploy tonight; the local `--serve` URL is enough to demo.

### Phase 5 — Docs + commit + merge (~2h)

- README rewrite — "Two surfaces, one tool layer." Architecture diagram. Midday-pattern callout. Hermes-pattern credit (already there). Pi 2nd-surface positioning.
- HANDOFF.md §13 — Stack D pivot summary + current state + resume commands.
- `.planning/v6-plan.md` — changelog entry: `v6.1 — Stack D pivot post-cluster-4`.
- `.env.example` — add `KLERK_AGENT_MODE`.
- `docs/architecture.md` — update to two-surface picture.
- Commits (atomic per phase), push feature branch, merge to main.

### Total estimate

| Phase | Hours |
|---|---|
| 0 Reconcile | 0.5 |
| 1 Midday verbs | 2 |
| 2 Pi 2nd surface | 3 |
| 3 Studio dashboard | 6 |
| 4 textual-serve | 2 |
| 5 Docs + merge | 2 |
| **Total** | **15.5h** |

---

## Tonight-vs-later split (23:59 WIB tonight)

You have ~5-7 focused hours left. Brief floor is **already met** by what's on `main` (clusters 1-4 + v5 work). Everything in Stack D is differentiation polish.

**Tonight (target ~6h)**:

| Phase | What ships tonight | Hours |
|---|---|---|
| 0 | Reconcile + green baseline | 0.5 |
| 1 | `--agent` flag on 5 verbs: `search hybrid`, `write`, `contradict scan`, `drive sync`, `extract-actions` (new) | 1.5 |
| 2 (mini) | Pi extension on 5 tools (one per verb above) + `klerk-chat` smoke-test; skip ts-shell move + npm publish prep | 2 |
| 3 (skeleton) | 5-panel Textual layout — `files`, `chat`, `activity`, `kg`, `status` working live; `graph`, `eval`, `traces` stubbed with placeholder data | 1.5 |
| 5 (lite) | README updated with new architecture diagram + screenshot of Bloomberg layout; HANDOFF §13; commit + merge to main | 0.5 |

**Tonight cut list** (defer to next week):
- `--agent` on the long-tail verbs (BM25, vector, anomaly, faq, eval, kg, index stats)
- ts-shell → cli/ move (just `pnpm run build` in `experimental/ts-shell/` for now)
- npm publish prep for klerk-cli
- textual-serve `--serve` mode (works locally; reviewer can run `--lite` for now)
- Phoenix sqlite integration in traces panel (placeholder text tonight)
- KG-from-drive-sync wiring (panel reads cached snapshot tonight)
- WS event bus (panels read JSONL tail tonight, simpler)
- Fly.io + Cloudflare Access docs
- Theme switcher (`cyberpunk-dark` is default and only theme tonight)

**Week 1 post-submission**: Phase 2 finish (ts-shell promotion, publish prep), Phase 3 polish (graph sparklines live, eval/traces real data, WS event bus), Phase 4 (textual-serve + Fly demo URL).

**Week 2 post-submission**: theme switcher, alternate panel layouts, KG graph viz (if time), demo recording.

---

## Decision log

### Why preserve cluster 4 (don't replace `/chat` with Pi-via-RPC)

- Cluster 4 is **already done and tested**. Discarding 5h of working code on the deadline is reckless.
- LangGraph's explicit graph semantics for fan-out (`MAX_TOOL_HOPS=4`, search_hybrid pre-seeding) are exactly what Pi philosophically refuses. The brief's `/chat` benefits from the explicit graph.
- "Two surfaces" reads as a deliberate architectural choice in the README, not a hack. "We replaced our Python with a Node sidecar to drive the brief's required FastAPI endpoint" would raise eyebrows.

### Why Pi flat loop + CLI-verb tools (not Pi with embedded LangGraph subagents)

- Pi's philosophy: no graphs, no subagents in core. Forcing LangGraph inside Pi via the third-party `tintinweb/pi-subagents` extension fights the framework.
- Pi tools shelling out to CLI verbs is the **Midday pattern verbatim**. Industry-validated by Midday CLI, Claude Code, Cursor, Codex.
- The doc-writer's 7-stage adversarial pipeline stays in Python where it belongs; Pi calls it as one tool invocation; the user sees a single "drafting…" progress indicator.

### Why Textual stays (don't pivot to React)

- 17h budget for React port + state management + theming + auth + WS bus + deploy — wouldn't fit in 4 months, let alone tonight.
- textual-serve gives us browser embed for free; Hermes Agent's web dashboard validates the "real TUI in browser via xterm.js" pattern as the gold standard.
- Reference projects (Harlequin, Posting, Dolphie, Elia) demonstrate the visual ambition is achievable in Textual.
- KG view, file explorer, sparkline graphs all have first-class Textual widgets.

### Why Midday-pattern (not MCP) as the tool contract

- Pi explicitly rejects MCP. Forcing MCP would mean a separate adapter layer Pi doesn't want.
- MCP requires a server process; CLI shellout requires nothing but a CLI binary + a flag.
- Reviewer-visible: `klerk search hybrid --agent --json "query"` runs in any shell. MCP requires installing an MCP client. The CLI contract is more universal.
- We can still ship an MCP server (we already have `src/klerk/mcp/server.py` for Claude Desktop integration); the MCP server itself becomes a thin wrapper over the CLI verbs.

### Why 5+ panel dashboard (not single-pane chat)

- Brief differentiation: every other CLI agent in 2026 (Hermes, Pi, Goose, Aider, Continue, Cursor, Claude Code) is single-pane chat or chat + sidebar. **Nobody ships a 5-panel observability dashboard.** That's the wedge.
- Reviewer (Mas Yanitra, an Indonesian-Japanese tech firm) will spend ≤30min on the codebase. A live Bloomberg-style dashboard during the `docker compose up` walkthrough = "this person thinks like an ops engineer, not just an ML engineer." That signal is worth disproportionately more than another agentic capability.
- KG view in the dashboard is unique (verified by Agent D's survey — zero competitors ship it).

### Rejected alternatives (do not revisit without new evidence)

- **Pi as primary orchestrator (Stack A)**: would require dropping cluster 4 work and adding Node-runtime tax to FastAPI's Python critical path.
- **Pi with embedded subagents via tintinweb/pi-subagents**: works but fights Pi's design philosophy + duplicates LangGraph's job.
- **React dashboard port**: 17h+ rewrite, no time, no payoff vs textual-serve.
- **Maestro for multi-panel multiplexing**: actually a tmux wrapper despite the "Bloomberg Terminal for CLI Agents" marketing.
- **MCP-over-stdio as the tool contract**: Pi rejects MCP; CLI shellout is more universal.
- **Stack E hand-rolled Python harness (Hermes-style)**: Hermes is Python + Rich, but writing our own agent loop wastes the cluster 4 LangGraph investment and the Pi 2nd-surface story.

---

## Risks (Stack D-specific, beyond v6 plan risks)

| Risk | Likelihood | Mitigation |
|---|---|---|
| Pi shell-out subprocess latency adds 50-100ms per tool call | Low-Medium | Acceptable for chat UX (Nemotron RTT dominates); persistent Pi process keeps tools warm |
| `--agent` flag inconsistently applied across 13 verbs → broken Pi tools | Medium | Phase 1 tests assert exit codes + JSON shape per verb; Pi tool catches non-zero exit and surfaces stderr |
| Two surfaces drift in behavior (different system prompts, different memory) | Medium | Document the divergence in README "Two surfaces" section; eval set covers FastAPI path (the brief floor); Pi surface is positioned as developer convenience, not parity |
| Textual 9-widget concurrent refresh causes flicker | Low | Textual's compositor handles partial-region diffing (Agent C confirmed); test under `KLERK_TUI_PROFILE=1` |
| disler-style WS bus adds reliability risk to activity panel | Low | Tonight: panel reads JSONL tail directly (no WS); WS upgrade in week 1 |
| Phoenix sqlite path varies across environments → traces panel broken | Low | Tonight: traces panel shows "Phoenix configured at <path>" with `[Open in browser]` button only; full integration in week 1 |
| Pi 0.78 `@earendil-works/*` API drift from 0.73 | Medium | Verify `dist/index.d.ts` matches integration BEFORE the rewrite; pin to exact 0.78.x |
| Reviewer environment doesn't have Node → can't run klerk-chat | Low (acceptable) | Brief mandates only `docker compose up`; klerk-chat is a developer differentiator, not a brief floor item |

---

## File touch list (Stack D delta over Stack C)

```
NEW
src/klerk/cli/_agent_flag.py                 ~40 LOC   --agent decorator
src/klerk/cli/extract_actions_cmd.py         ~30 LOC   new verb
src/klerk/studio/theme.py                    ~50 LOC   cyberpunk-dark palette
src/klerk/studio/widgets/files.py            ~120 LOC  Harlequin tree
src/klerk/studio/widgets/live_chat.py        ~200 LOC  (already in v6 plan)
src/klerk/studio/widgets/activity.py         ~80 LOC   (already in v6 plan)
src/klerk/studio/widgets/graph.py            ~100 LOC  sparklines
src/klerk/studio/widgets/kg_snapshot.py      ~80 LOC
src/klerk/studio/widgets/eval_panel.py       ~80 LOC
src/klerk/studio/widgets/traces.py           ~60 LOC
src/klerk/studio/widgets/status_bar.py       ~40 LOC
src/klerk/api/events.py                      ~80 LOC   WS event bus (week 1)
cli/README.md                                ~60 LOC
tests/test_agent_mode.py                     ~80 LOC

MODIFIED (Stack C plan → Stack D delta)
src/klerk/cli/main.py                        apply @with_agent_mode to 13 verbs
src/klerk/api/server.py                      drop /internal/* (never built); add /events/ws (week 1)
src/klerk/studio/app.py                      replace grid layout, swap in 9 widgets, theme apply
experimental/pi-extension/src/tools/*.ts     subprocess shell-out instead of HTTP
experimental/pi-extension/src/system-prompt  rewrite to enumerate CLI verbs
README.md                                    "Two surfaces, one tool layer" section + new arch diagram
HANDOFF.md                                   §13 Stack D pivot summary
.planning/v6-plan.md                         v6.1 changelog entry

DROPPED FROM v6 PLAN
src/klerk/agent/orchestrator.py              (cluster 4 already shipped; preserve)
src/klerk/agent/tools.py                     (cluster 4 already shipped; preserve)
src/klerk/api/server.py /internal/*          (never built; replaced by CLI shellout)
src/klerk/studio/widgets/sessions.py         (deferred; chat panel handles session switch)

MOVED (week 1)
experimental/ts-shell/                       → cli/  (top-level)
```

---

## Sources (research backing this plan)

- [Pi agent SDK docs](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md) — `createAgentSession`, `defineTool`, RPC mode
- [Pi RPC protocol](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md)
- [Mario Zechner — Pi philosophy](https://mariozechner.at/posts/2025-12-22-year-in-review-2025/) — flat loop, no graphs, no subagents in core
- [Armin Ronacher — Pi in OpenClaw](https://lucumr.pocoo.org/2026/1/31/pi/)
- [Midday CLI package](https://github.com/midday-ai/midday/tree/main/packages/cli) — `--agent` flag pattern
- [Writing CLI tools that AI agents want to use (DEV.to)](https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no)
- [Rewrite your CLI for AI agents — Justin Poehnelt](https://justin.poehnelt.com/posts/rewrite-your-cli-for-ai-agents/)
- [textual-serve repo](https://github.com/Textualize/textual-serve) — v1.1.3, WS subprocess model
- [Textual v4 streaming Markdown (Simon Willison)](https://simonwillison.net/2025/Jul/22/textual-v4/) — explicit LLM-streaming support
- [disler/claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability) — Activity event-bus pattern
- [Hermes Agent web dashboard](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/web-dashboard.md) — React + xterm.js wrapping real TUI
- Reference TUIs: [Harlequin](https://harlequin.sh/) · [Posting](https://posting.sh/) · [Dolphie](https://github.com/charles-001/dolphie)
