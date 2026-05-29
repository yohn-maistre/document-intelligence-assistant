"""klerk Typer CLI — primary brand surface.

Verbs are opinionated, output is structured (Rich tables for humans, --json for
agents). The chat REPL is one entry point; the verbs are the headline.
"""

from __future__ import annotations

import os
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from klerk import __version__

app = typer.Typer(
    name="klerk",
    help="Document Intelligence Assistant — multi-agent RAG over your documents.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


# ─── Stub subcommand groups (filled in over h1-h22) ──────────────────────────
synth_app = typer.Typer(name="synth", help="Synthetic corpus generation.", no_args_is_help=True)
index_app = typer.Typer(name="index", help="Build / inspect the retrieval index.", no_args_is_help=True)
search_app = typer.Typer(name="search", help="Hybrid / vector / BM25 search.", no_args_is_help=True)
drive_app = typer.Typer(name="drive", help="Google Drive ingestion.", no_args_is_help=True)
eval_app = typer.Typer(name="eval", help="RAGAS + custom rubric + SEA-HELM eval.", no_args_is_help=True)
trace_app = typer.Typer(name="trace", help="Phoenix trace inspection.", no_args_is_help=True)
bg_app = typer.Typer(name="bg", help="Background ingestion agent.", no_args_is_help=True)
kg_app = typer.Typer(name="kg", help="Knowledge graph extraction + inspection.", no_args_is_help=True)

app.add_typer(synth_app)
app.add_typer(index_app)
app.add_typer(search_app)
app.add_typer(drive_app)
app.add_typer(eval_app)
app.add_typer(trace_app)
app.add_typer(bg_app)
app.add_typer(kg_app)

# ── Single-verb commands attached at top level ──
from klerk.cli.parse_cmd import parse_cmd  # noqa: E402
from klerk.cli.ask_cmd import ask_cmd  # noqa: E402
from klerk.cli.propose_cmd import propose_cmd  # noqa: E402
from klerk.cli.contradict_cmd import scan_cmd as contradict_scan_cmd  # noqa: E402
from klerk.cli.faq_cmd import build_cmd as faq_build_cmd  # noqa: E402
from klerk.cli import index_cmd, search_cmd, kg_cmd  # noqa: E402

app.command("parse", help="Parse one file (Docling / native / PyMuPDF fallback).")(parse_cmd)

# index subcommands
index_app.command("build", help="Parse + chunk + embed + upsert.")(index_cmd.build)
index_app.command("stats", help="Show current corpus stats.")(index_cmd.show_stats)

# search subcommands
search_app.command("bm25", help="BM25 search (LanceDB native FTS).")(search_cmd.bm25)
search_app.command("vector", help="Vector search (BGE-M3 + LanceDB cosine).")(search_cmd.vector)
search_app.command("hybrid", help="Hybrid: vector + BM25 + RRF + BGE-Reranker.")(search_cmd.hybrid)

# kg subcommands
kg_app.command("extract", help="Build the KG over every indexed chunk.")(kg_cmd.extract)
kg_app.command("stats", help="Show KG entity/relation counts.")(kg_cmd.stats)
kg_app.command("show", help="Print entities + relations (Rich panels).")(kg_cmd.show)

# contradict + faq subcommand groups
contradict_app = typer.Typer(name="contradict", help="Pairwise contradiction scan over the KG.", no_args_is_help=True)
faq_app = typer.Typer(name="faq", help="Corpus Learning Agent — auto-FAQ.", no_args_is_help=True)
app.add_typer(contradict_app)
app.add_typer(faq_app)

contradict_app.command("scan", help="Run the contradiction sweep, write the report.")(contradict_scan_cmd)
faq_app.command("build", help="Propose questions per doc + answer them with citations.")(faq_build_cmd)

# eval subcommand
from klerk.cli.eval_cmd import run_cmd as eval_run_cmd  # noqa: E402

eval_app.command("run", help="Run RAGAS + 5-axis rubric + SEA-HELM-style Bahasa parity.")(eval_run_cmd)


# ─── Top-level utility verbs ─────────────────────────────────────────────────
@app.command()
def version() -> None:
    """Print klerk version."""
    console.print(f"klerk {__version__}")


@app.command()
def smoke() -> None:
    """h0 smoke-test: LiteLLM → Nemotron round-trip + Phoenix launch.

    Verifies the gateway is reachable and the observability stack boots.
    Safe to run repeatedly; emits cache hits on subsequent runs once caching
    is wired in h16.5.
    """
    from klerk.llm.nemotron import NemotronConfig
    from klerk.llm.router import complete

    console.print(
        Panel.fit(
            "[bold cyan]klerk smoke-test[/bold cyan]\n"
            "Verifying gateway → Nemotron round-trip and Phoenix boot.",
            border_style="cyan",
        )
    )

    # ── 1. Config check ──
    cfg = NemotronConfig.from_env()
    table = Table(title="Config", show_header=False, border_style="dim")
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("base_url", cfg.base_url)
    table.add_row("model", cfg.model)
    table.add_row("api_key", "***set***" if cfg.api_key else "[red](not set — export NVIDIA_API_KEY)[/red]")
    console.print(table)

    if not cfg.api_key:
        console.print(
            "\n[yellow]NVIDIA_API_KEY not set; skipping live LLM round-trip. "
            "Copy .env.example to .env and fill in the key to enable.[/yellow]"
        )
        _phoenix_section()
        raise typer.Exit(code=0)

    # ── 2. Live LLM round-trip ──
    console.print("\n[dim]Calling Nemotron via LiteLLM...[/dim]")
    try:
        response = complete(
            messages=[
                {"role": "system", "content": "You answer in one short sentence."},
                {"role": "user", "content": "Say 'klerk is online.' and nothing else."},
            ],
            max_tokens=32,
        )
        reply = response.choices[0].message.content
        console.print(Panel(reply, title="Nemotron reply", border_style="green"))
    except Exception as e:  # noqa: BLE001
        console.print(Panel(f"[red]{type(e).__name__}: {e}[/red]", title="LiteLLM error", border_style="red"))
        raise typer.Exit(code=1) from e

    _phoenix_section()


def _phoenix_section() -> None:
    """Boot Phoenix and show the URL, but don't block the smoke verb."""
    console.print("\n[dim]Booting Arize Phoenix...[/dim]")
    try:
        from klerk.obs.phoenix import instrument_litellm, launch

        instrument_litellm()
        url = launch()
        console.print(Panel(url, title="Phoenix UI", border_style="green"))
        console.print("[dim]Phoenix is running in-process; it stops when this CLI exits.[/dim]")
    except Exception as e:  # noqa: BLE001
        console.print(
            Panel(
                f"[yellow]{type(e).__name__}: {e}[/yellow]\n"
                "Phoenix init failed — non-fatal for the smoke verb.",
                title="Phoenix warning",
                border_style="yellow",
            )
        )


# ─── Chat passthrough (h19.5–22 wires this to klerk-cli/Pi) ─────────────────
@app.command()
def chat(
    locale: Annotated[str, typer.Option("--locale", "-l", help="en | id")] = "en",
) -> None:
    """Open the klerk chat REPL (delegates to klerk-cli; Pi runs hidden).

    Until h19.5, this prints a placeholder.
    """
    _ = locale
    console.print(
        Panel.fit(
            "[bold]klerk chat[/bold] is wired in h19.5–22.\n"
            "Until then, use the verbs: [cyan]klerk ask[/cyan] / [cyan]klerk propose[/cyan].",
            border_style="dim",
        )
    )


# ─── Q&A and proposal verbs ──────────────────────────────────────────────────
app.command("ask", help="Q&A over the corpus (CRAG-lite + citations).")(ask_cmd)
app.command("propose", help="Adversarial proposal pipeline (Drafter-A vs Drafter-B + Adjudicator + Critic).")(propose_cmd)


def main() -> None:
    """Entry point exposed via [project.scripts] klerk = ..."""
    os.environ.setdefault("LITELLM_LOG", "WARNING")
    app()


if __name__ == "__main__":
    main()
