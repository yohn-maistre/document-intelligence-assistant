# Explorations — what we built, what we learned, what we didn't ship

This file is the honest record of detours taken while building klerk that did
**not** make it into the shipped product. The brief warns against
over-engineering; this is where we account for the things we tried, why they
were attractive, and why we cut them. Nothing here is in the runtime, in
`docker compose up`, or in CI. Git history is the full record — the archived
trees under `ts-archive/` are kept as readable artifacts, not living code.

## The v6 detour: a TypeScript second surface (Pi / Node)

### What we explored

For a stretch (the v6 plan, now superseded), the plan called for a **second
UI surface** built in TypeScript on Node:

- **`ts-archive/ts-shell/`** — a polished TypeScript CLI shell (formerly
  `klerk-cli/`). The framing was "klerk runs on hardware" (Pi-as-runtime): a
  thin TS chat shell delegating to a hidden Python runtime over a subprocess /
  socket boundary.
- **`ts-archive/pi-extension/`** — a Pi contributor npm extension packaging the
  same chat surface as a Pi plugin (formerly `pi-extension-klerk/`).

The pitch was genuine: a TS surface looks modern, Pi gives a fast TUI scaffold,
and "the agent runs on a Raspberry Pi" is a memorable demo hook.

### What we learned

Four threads of research (captured in `.planning/archive/`) converged on the
same verdict — the Node/TS second surface costs more than it returns:

1. **Pi is vertical-stack only.** Pi's TUI primitives don't do horizontal,
   multi-pane layouts. A Bloomberg-style operator dashboard (Files / Chat /
   Activity / Status / Traces side by side) is simply not expressible in Pi.
   The one feature we wanted most was the one Pi couldn't give us.
2. **The Node tax is real.** A TS surface means a second toolchain (pnpm,
   tsconfig, lockfiles), a second language in the repo, a second test/lint/CI
   path, and a subprocess or socket boundary between the shell and the Python
   engine — which pays Python startup + model-reload cost on the hot path, or
   forces an HTTP shim we'd then have to maintain and test.
3. **The ecosystem gaps are non-negotiable.** A full TS+Bun rewrite (the
   further-out option) hits hard walls: `@lancedb/lancedb` on Bun is REST-only,
   there's no BM25/Tantivy FTS in JS, and no ColBERT reranker in TS. The
   retrieval quality that makes klerk good lives in the Python stack.
4. **Two surfaces, one substrate is achievable in Python alone.** `textual`
   (>= 0.86) ships `textual serve` / the `textual-serve` package, which runs a
   Textual TUI as a **server-side Python process** and streams the rendered
   terminal to the browser over a websocket (xterm.js wrapper). That gives us
   the exact second surface we wanted — the same TUI, in a browser — with the
   same in-process engine access as the terminal, **no Node, no HTTP shim**.

### What we shipped instead (v7)

One Python substrate, two surfaces:

- **Terminal**: `klerk chat` / `klerk-studio` runs the Textual Studio TUI.
- **Browser**: `textual serve "klerk.studio.app:main"` serves the *same* Studio
  on `:8001`, alongside FastAPI on `:8000`, from the one container.

This deletes the entire Node toolchain, the subprocess/socket boundary, and the
`/internal/*` HTTP shim the v6 plan had assumed textual-serve would need (it
doesn't — see `.planning/v7-plan.md` §7, delta D2). Less code, one language,
the dashboard layout we actually wanted, and no second model load.

The TS+Bun full rewrite (Flue / Mastra / Bun-as-runtime) is a **separate, much
larger exploration** (estimated 6-9 weeks) left explicitly as a future
direction, not part of klerk's submission. The v7 architecture stays
"Phase-C-friendly" — the Midday-style `--agent --json` CLI contract means a
future TS agent layer could wrap the Python core via `Bun.spawn` without
rewriting it — but that is a post-submission spike, not shipped work.

## Why this is in `docs/`, not deleted

Keeping these trees in `experimental/` would imply ongoing investment we're not
making. Deleting them outright would erase the reasoning. Archiving them under
`docs/explorations/` with this narrative is the honest middle: the exploration
is visible and creditable, but it's clearly labeled as not-shipped. This
matches the brief's anti-over-engineering stance — we'd rather show the cut than
hide it or ship it.

## Other demoted code (still in `experimental/`)

Separate from the TS detour, a handful of loose Python files remain in
`experimental/` — APScheduler local-watch ingestion (`background.py`),
SQLite resumability checkpointing (`checkpoint.py`), a PageRank rerank
tiebreaker (`pagerank.py`), and a SEA-HELM Bahasa parity runner
(`seahelm_runner.py`). Those were demoted for being out of brief scope rather
than being a wrong-substrate bet; see `experimental/README.md` for each one's
demotion rationale and re-trigger condition.
