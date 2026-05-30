.PHONY: help setup demo eval mcp studio studio-web phoenix api compose compose-down clean

help:
	@echo "klerk — Document Intelligence Assistant"
	@echo ""
	@echo "  setup          install Python deps (uv sync)"
	@echo "  smoke          h0 smoke-test: LiteLLM → Nemotron + Phoenix launch"
	@echo "  demo           end-to-end on data/seed: index → kg → ask → propose → contradict → faq → anomaly"
	@echo "  eval           RAGAS + klerk 5-axis rubric"
	@echo "  kg             rebuild KG + render kg.html"
	@echo "  contradict     pairwise contradiction sweep over the KG"
	@echo "  faq            Corpus Learning Agent → auto-FAQ"
	@echo "  anomaly        z-score outlier detection + LLM justifications"
	@echo "  api            run the FastAPI server locally (uvicorn :8000)"
	@echo "  compose        docker compose up --build (FastAPI + Phoenix in one container)"
	@echo "  compose-down   stop + remove the docker compose stack"
	@echo "  mcp            klerk-mcp (stdio) — point Claude Desktop / Goose / Cursor at it"
	@echo "  studio         Textual operator TUI"
	@echo "  studio-web     Browser deploy via textual serve (textual >=0.86)"
	@echo "  phoenix        open Arize Phoenix UI on local traces"
	@echo "  clean          wipe caches, lancedb, parsed/, output/"
	@echo ""
	@echo "  experimental/  archived TS shell + Pi extension + APScheduler bg + checkpoint db."
	@echo "                 See experimental/README.md for what lives there and why."

setup:
	uv sync --extra dev
	@echo "✓ klerk setup complete"

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
	uv run python -m klerk.cli.main eval run --ragas --rubric

api:
	uv run klerk-api

compose:
	docker compose up --build

compose-down:
	docker compose down

mcp:
	uv run klerk-mcp

studio:
	uv run klerk-studio

studio-web:
	uv run textual serve "src/klerk/studio/app.py:main"

phoenix:
	uv run python -c "import phoenix as px; px.launch_app()"

kg:
	uv run klerk kg extract --rebuild
	uv run klerk kg viz

contradict:
	uv run klerk contradict scan

faq:
	uv run klerk faq build

anomaly:
	uv run klerk anomaly scan

clean:
	rm -rf .lancedb .diskcache .phoenix .gptcache
	rm -rf data/parsed data/output data/synth/.cache
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf **/__pycache__ **/*.pyc
	find . -name "*.sqlite*" -delete
	@echo "✓ caches and ephemeral data cleaned"
