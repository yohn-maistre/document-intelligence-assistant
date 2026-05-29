.PHONY: help setup setup-py setup-ts demo eval mcp studio studio-web phoenix bg clean

help:
	@echo "klerk — Document Intelligence Assistant"
	@echo ""
	@echo "  setup          install Python + TS deps (uv sync + pnpm install)"
	@echo "  smoke          h0 smoke-test: LiteLLM → Nemotron + Phoenix launch"
	@echo "  demo           end-to-end on data/seed: index → kg → ask → propose → contradict → faq → anomaly"
	@echo "  eval           RAGAS + custom 5-axis rubric + SEA-HELM-style Bahasa parity"
	@echo "  kg             rebuild KG + render kg.html"
	@echo "  contradict     pairwise contradiction sweep over the KG"
	@echo "  faq            Corpus Learning Agent → auto-FAQ"
	@echo "  anomaly        z-score outlier detection + LLM justifications"
	@echo "  bg             foreground APScheduler watch loop on data/raw/"
	@echo "  bg-once        one ingestion cycle then exit (CI / cron mode)"
	@echo "  mcp            klerk-mcp (stdio) — point Claude Desktop / Goose / Cursor at it"
	@echo "  studio         Textual operator TUI (5 panels)"
	@echo "  studio-web     STRETCH: browser deploy via textual-web (separate venv)"
	@echo "  phoenix        open Arize Phoenix UI on local traces"
	@echo "  local-llm      STRETCH: on-prem Bahasa LLM setup (llama.cpp + Gemma 3 / Qwen 3.5)"
	@echo "  clean          wipe caches, lancedb, parsed/, output/, checkpoint db"

setup: setup-py setup-ts
	@echo "✓ klerk setup complete"

setup-py:
	uv sync --extra dev

setup-ts:
	pnpm install

smoke:
	uv run python -m klerk.cli.main smoke

demo:
	@echo "── 1. index the seed corpus ──"
	uv run klerk index build --src data/seed --rebuild
	@echo "── 2. extract a KG ──"
	uv run klerk kg extract --rebuild
	@echo "── 3. Bahasa single-doc ──"
	uv run klerk ask "Berapa tarif konsultan advisory PT Pelangi per jam?" --locale id
	@echo "── 4. EN multi-hop ──"
	uv run klerk ask "Why did Q1 consultant spend overrun by 29% — was it a rate issue or a volume issue?"
	@echo "── 5. adversarial proposal ──"
	uv run klerk propose "Q1 budget variance — consultant spend + parental leave coverage" -n 3
	@echo "── 6. contradiction sweep + FAQ ──"
	uv run klerk contradict scan
	uv run klerk faq build
	@echo "── 7. anomaly scan ──"
	uv run klerk anomaly scan || true
	@echo ""
	@echo "✓ demo complete. Inspect outputs:"
	@echo "    data/output/proposals/   — proposal markdown"
	@echo "    data/output/contradictions.md  data/output/faq.md  data/output/anomalies.md"
	@echo "    Then: make studio"

eval:
	uv run python -m klerk.cli.main eval run --ragas --rubric --seahelm

mcp:
	uv run klerk-mcp

studio:
	uv run klerk-studio

studio-web:
	uv run klerk-studio --serve

phoenix:
	uv run python -c "import phoenix as px; px.launch_app()"

bg:
	uv run klerk bg start

bg-once:
	uv run klerk bg start --once

kg:
	uv run klerk kg extract --rebuild
	uv run klerk kg viz

contradict:
	uv run klerk contradict scan

faq:
	uv run klerk faq build

anomaly:
	uv run klerk anomaly scan

local-llm:
	@echo "Set up an on-prem Bahasa-strong LLM (STRETCH item 26):"
	@echo "  scripts/setup-local-llm.sh help"
	@echo "  scripts/setup-local-llm.sh all   # install + download + serve"

clean:
	rm -rf .lancedb .diskcache .phoenix .gptcache
	rm -rf data/parsed data/output data/synth/.cache
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf **/__pycache__ **/*.pyc
	find . -name "*.sqlite*" -delete
	@echo "✓ caches and ephemeral data cleaned"
