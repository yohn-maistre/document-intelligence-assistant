# Next-session boot doc

> Read this first. Then `HANDOFF.md` §1 + §13. Then `.planning/v7-plan.md` (full work breakdown).

## State

- `main` = `claude/agent-framework-planning-jJqQj` (same SHA after the push that lands this file)
- Phase A.0 done (RQYyt merged into main at `740cddd`; D1-D6 deltas applied; v6 + stack-d archived to `.planning/archive/`; HANDOFF.md §13 written)
- Phase A.1-A.5 pending — five parallel work streams, ~5h wall tonight
- **Deadline: 31 May 2026 morning Jakarta** (recruiter-negotiated from brief literal 30 Sep)

## Your default role: S0 coordinator

Integrate the parallel sessions, own merges, write README + HANDOFF v7 refresh + submission email.

If you'd rather pick a single Phase A worker session instead, see `.planning/v7-plan.md` §6 for file ownership and pick one:

- **S1** — Midday CLI `--agent --json` decorator + new verbs `klerk extract-actions` (Brief Option B) + `klerk escalate draft` (Brief Option A)
- **S2** — Memory trio (`src/klerk/memory/{__init__, store}.py` + SOUL.md/MEMORY.md/LanceDB recall + orchestrator prefix patch)
- **S3** — Studio Bloomberg dashboard, **floor first** (Chat / Files / Activity / Status / Traces), bonus only if floor green
- **S4** — Docker delta (drop Node from image, add textual-serve, tini supervisor, dual-port :8000+:8001) + archive `experimental/{pi-extension, ts-shell}` → `docs/explorations/ts-archive/`
- **S5** — `pyproject.toml` extras (`lite/server/local/full`) + `EmbedBackend` ABC polish + XDG paths

## First concrete actions (S0)

1. Sanity check:
   ```bash
   git log -1 --oneline        # latest commit on planning branch
   git status                  # clean tree
   uv sync                     # Python deps
   pytest -q tests/ -x         # ~143 + RQYyt new tests; some need LITELLM_KEY
   ```

2. Decide spawn cadence — parallel via SDK call (preferred for the 4× speedup) or serial within this session. The plan assumes parallel.

3. Start **S1 (Midday CLI verbs)** first regardless — no dependencies on other sessions, unblocks the rest.

4. Open an atomic-commit tracker. One commit per task, conventional prefixes (`feat`, `fix`, `refactor`, `docs`, `chore`, `test`).

## Open env questions (resolve before spawning workers)

- `LITELLM_KEY` env var: present in `.env`? Needed for live LLM tests + the Phase B eval run.
- BGE-M3 model cached on disk? First-run download ~1.2GB at `~/.cache/huggingface/hub/models--BAAI--bge-m3/`.
- Drive service account JSON: path documented in README; confirm bind-mount works for `docker compose up`.

## Don't

- Add `/internal/*` HTTP routes — dropped per D2.
- Shell out from the orchestrator's tools to CLI verbs — D1: in-process only. `src/klerk/agent/tools.py` is already correct.
- Touch `experimental/` until S4 owns the archive move (avoids merge thrash).
- Ship `doc_writer` (`klerk write`) as a brief-aligned core feature — D4 bonus only; label accordingly in README + EVAL.
- Add `/memory/*` HTTP routes in Phase A — D3 bonus, Phase B if slack.

## Where prior decisions live

- Four-agent research (Pi / Flue / Midday / TS+Bun) synthesised in `.planning/v7-plan.md` §1; depth lives in `.planning/archive/v6-plan.md` (decision log) and `.planning/archive/stack-d-migration.md` (research findings).
- v6 / Stack-D = superseded by v7 per the D1-D6 strategy deltas; archives kept for trace.
- v4 plan + post-step-11 plan = in the plan-mode scratch file outside the repo (`~/.claude/plans/root-claude-uploads-…md`), not committed.

## Brief reminder

- Submission: public GitHub repo URL + Drive folder ID (Editor-shared with `ydharmaw@fata-organa.com`) + 1-paragraph self-assessment + hardware notes + "connected to Nemotron proxy successfully" line.
- Use ONLY `nemotron-3-nano-omni` via the LiteLLM proxy. No OpenAI / Anthropic / Cohere fallbacks.
- Brief floor satisfied on main already (`740cddd`). v7 polish is differentiation; if Phase A overruns we ship from main.
