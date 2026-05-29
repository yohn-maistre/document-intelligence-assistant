# klerk

**Document Intelligence Assistant** — multi-agent RAG over your documents with hybrid retrieval, knowledge-graph extraction, adversarial proposal pipeline, and a polished operator TUI.

> Take-home for the Middle AI Engineer role at **PT Fata Organa Solusi**, May 2026.
> _README is a placeholder during scaffolding; full content lands in h31._

## Status

Day 1 / h0 — scaffolding in progress.

## Quickstart (eventual)

```bash
make setup       # uv sync + pnpm install
make smoke       # LiteLLM → Nemotron + Phoenix launch check
make demo        # end-to-end: synth → index → ask + propose
make eval        # RAGAS + custom rubric + SEA-HELM Bahasa
```

## Four surfaces, one backend

```
CLI verbs (primary brand)   →   klerk ask · klerk propose · klerk synth gen · ...
Chat shell                  →   klerk chat   (Ink shell, Pi as hidden runtime)
MCP gateway                 →   klerk-mcp    (stdio, Hermes-pattern)
Studio TUI                  →   klerk studio (Textual; --serve for browser)
```

See `/root/.claude/plans/root-claude-uploads-6b70b1bf-d52d-4f10-imperative-hickey.md` for the full plan.
