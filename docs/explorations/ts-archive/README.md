# ts-archive/ — archived TypeScript experiments

These directories are **archived experiments**, not living code. They were moved
here (via `git mv`, so history is preserved) from `experimental/` during the v7
cleanup pass. Nothing here is imported by the runtime, built by the Docker
image, exercised by CI, or part of `docker compose up`.

## What's here

- **`pi-extension/`** — a Pi contributor npm extension (formerly
  `experimental/pi-extension/`, originally `pi-extension-klerk/`). Packaged a
  klerk chat surface as a Pi plugin.
- **`ts-shell/`** — a TypeScript CLI chat shell (formerly
  `experimental/ts-shell/`, originally `klerk-cli/`). Delegated to a hidden
  Python runtime under the "klerk runs on a Pi" framing.

## Why they're archived, not deleted

The v6 plan called for a TypeScript second surface (Pi / Node). v7 chose
`textual-serve` instead — one Python substrate serving both a terminal TUI and
the same TUI in the browser — which is less code, one language, supports the
multi-pane dashboard Pi couldn't, and drops the Node toolchain entirely. The
full reasoning ("explored, learned, didn't ship") is in
[`../EXPLORATIONS.md`](../EXPLORATIONS.md).

We keep these as readable artifacts so the exploration is creditable and the
decision is auditable. They are **not maintained** — treat them as a snapshot.

## Git history is the record

The authoritative record of how these came to be and why they were cut lives in
the commit history. To trace them:

```sh
# Follow a file across the rename from experimental/ to here:
git log --follow -- docs/explorations/ts-archive/ts-shell/src/index.ts

# See the v6 plan and the research that drove the cut:
git log -- .planning/archive/
```

If a future effort wants a TS/Pi surface (e.g. a post-submission Phase C
TS+Bun spike), start from these as a template and the `--agent --json` CLI
contract as the integration boundary — but expect to update them; the
ecosystems will have moved on.
