.PHONY: help setup setup-py setup-ts demo eval mcp studio studio-web phoenix bg clean

help:
	@echo "klerk — Document Intelligence Assistant"
	@echo ""
	@echo "  make setup        install Python + TS deps (uv sync + pnpm install)"
	@echo "  make smoke        h0 smoke-test: LiteLLM → Nemotron, Phoenix launch"
	@echo "  make demo         end-to-end: synth → index → ask + propose"
	@echo "  make eval         run RAGAS + custom rubric + SEA-HELM Bahasa eval"
	@echo "  make mcp          start the MCP server (stdio)"
	@echo "  make studio       start the Textual operator TUI"
	@echo "  make studio-web   serve the studio in a browser (textual-web)"
	@echo "  make phoenix      open Arize Phoenix UI on local traces"
	@echo "  make bg           start the Background Ingestion Agent"
	@echo "  make clean        wipe caches, lancedb, parsed/, output/"

setup: setup-py setup-ts
	@echo "✓ klerk setup complete"

setup-py:
	uv sync --extra dev

setup-ts:
	pnpm install

smoke:
	uv run python -m klerk.cli.main smoke

demo:
	uv run python -m klerk.cli.main synth gen --universe all --cached
	uv run python -m klerk.cli.main index build --rebuild
	uv run python -m klerk.cli.main ask "Berapa lama cuti melahirkan Acme?"
	uv run python -m klerk.cli.main ask "How does Meridian's grant compliance interact with their audit findings?"
	uv run python -m klerk.cli.main propose "Pelangi IP clause renegotiation" --sections 3

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
	uv run python -m klerk.cli.main bg start

clean:
	rm -rf .lancedb .diskcache .phoenix .gptcache
	rm -rf data/parsed data/output data/synth/.cache
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf **/__pycache__ **/*.pyc
	find . -name "*.sqlite*" -delete
	@echo "✓ caches and ephemeral data cleaned"
