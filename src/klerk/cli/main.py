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
eval_app = typer.Typer(name="eval", help="RAGAS + custom 5-axis rubric.", no_args_is_help=True)
kg_app = typer.Typer(name="kg", help="Knowledge graph extraction + inspection.", no_args_is_help=True)

app.add_typer(synth_app)
app.add_typer(index_app)
app.add_typer(search_app)
app.add_typer(drive_app)
app.add_typer(eval_app)
app.add_typer(kg_app)

# ── Single-verb commands attached at top level ──
from klerk.cli.parse_cmd import parse_cmd  # noqa: E402
from klerk.cli.ask_cmd import ask_cmd  # noqa: E402
from klerk.cli.write_cmd import write_cmd  # noqa: E402
from klerk.cli.contradict_cmd import scan_cmd as contradict_scan_cmd  # noqa: E402
from klerk.cli.faq_cmd import build_cmd as faq_build_cmd  # noqa: E402
from klerk.cli import drive_cmd, index_cmd, search_cmd, kg_cmd  # noqa: E402

app.command("parse", help="Parse one file (Docling / native / PyMuPDF fallback).")(parse_cmd)

# synth subcommands
from klerk.cli.synth_cmd import check_cmd as synth_check_cmd, gen_cmd as synth_gen_cmd  # noqa: E402

synth_app.command("gen", help="Generate the 28-doc Fata Organa corpus.")(synth_gen_cmd)
synth_app.command("check", help="Verify the corpus plan satisfies the brief.")(synth_check_cmd)

# index subcommands
index_app.command("build", help="Parse + chunk + embed + upsert.")(index_cmd.build)
index_app.command("stats", help="Show current corpus stats.")(index_cmd.show_stats)

# search subcommands
search_app.command("bm25", help="BM25 search (LanceDB native FTS).")(search_cmd.bm25)
search_app.command("vector", help="Vector search (BGE-M3 + LanceDB cosine).")(search_cmd.vector)
search_app.command("hybrid", help="Hybrid: vector + BM25 + RRF + BGE-M3 ColBERT rerank.")(search_cmd.hybrid)

# kg subcommands
kg_app.command("extract", help="Build the KG over every indexed chunk.")(kg_cmd.extract)
kg_app.command("stats", help="Show KG entity/relation counts.")(kg_cmd.stats)
kg_app.command("show", help="Print entities + relations (Rich panels).")(kg_cmd.show)

# drive subcommands
drive_app.command("sync", help="Bootstrap-or-incremental sync the Drive folder.")(drive_cmd.sync_cmd)
drive_app.command("upload", help="Upload a corpus dir/file into Drive (supports --dry-run).")(drive_cmd.upload_cmd)
drive_app.command("status", help="Show the persisted manifest + page-token snapshot.")(drive_cmd.status_cmd)

# contradict + faq subcommand groups
contradict_app = typer.Typer(name="contradict", help="Pairwise contradiction scan over the KG.", no_args_is_help=True)
faq_app = typer.Typer(name="faq", help="Corpus Learning Agent — auto-FAQ.", no_args_is_help=True)
app.add_typer(contradict_app)
app.add_typer(faq_app)

contradict_app.command("scan", help="Run the contradiction sweep, write the report.")(contradict_scan_cmd)
faq_app.command("build", help="Propose questions per doc + answer them with citations.")(faq_build_cmd)

# eval subcommand
from klerk.cli.eval_cmd import run_cmd as eval_run_cmd  # noqa: E402

eval_app.command("run", help="Run RAGAS + klerk 5-axis rubric.")(eval_run_cmd)

# ── SHOULD-tier verbs: anomaly, kg viz ────────────────────────────────────
from klerk.cli.should_cmds import (  # noqa: E402
    anomaly_scan_cmd,
    kg_viz_cmd,
)

anomaly_app = typer.Typer(name="anomaly", help="Surface outlier docs that don't fit the corpus.", no_args_is_help=True)
app.add_typer(anomaly_app)
anomaly_app.command("scan", help="z-score scan over doc-centroid distances + LLM justifications.")(anomaly_scan_cmd)

kg_app.command("viz", help="Render the KG to interactive HTML (pyvis).")(kg_viz_cmd)


# ── studio ──────────────────────────────────────────────────────────────────
@app.command("studio", help="Launch the Bloomberg-style Textual cockpit (floor: files/chat/activity/status/traces).")
def studio_cmd(
    serve: Annotated[bool, typer.Option("--serve", help="Serve the studio in-browser via textual-serve (:8001).")] = False,
    lite: Annotated[bool, typer.Option("--lite", help="Chat-only layout for narrow (<120 col) terminals.")] = False,
    mode: Annotated[str, typer.Option("--mode", help="Engine mode: 'lite' (in-process orchestrator) or 'full' (SSE to /chat).")] = "lite",
    base_url: Annotated[str, typer.Option("--base-url", help="FastAPI base URL used by 'full' mode.")] = "http://localhost:8000",
    locale: Annotated[str, typer.Option("--locale", "-l", help="en | id")] = "en",
) -> None:
    """Open klerk studio — files / live-chat / activity / status / traces."""
    from klerk.studio import app as studio_app

    if serve:
        try:
            studio_app.serve(mode="full", base_url=base_url)
        except RuntimeError as e:
            console.print(f"[yellow]{e}[/yellow]")
            raise typer.Exit(code=1) from e
        return
    studio_app.run(mode=mode, base_url=base_url, locale=locale, lite=lite)


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
    table.add_row("api_key", "***set***" if cfg.api_key else "[red](not set — export LITELLM_KEY)[/red]")
    table.add_row(
        "cf_headers",
        "***set (CF_CLIENT_ID + CF_CLIENT_SECRET)***" if cfg.cf_headers else "[yellow](not set — proxy will 403)[/yellow]",
    )
    console.print(table)

    if not cfg.api_key:
        console.print(
            "\n[yellow]LITELLM_KEY not set; skipping live LLM round-trip. "
            "Copy .env.example to .env and fill in LITELLM_KEY + CF_CLIENT_ID + CF_CLIENT_SECRET to enable.[/yellow]"
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
            "Until then, use the verbs: [cyan]klerk ask[/cyan] / [cyan]klerk write[/cyan].",
            border_style="dim",
        )
    )


# ── memory (Hermes trio: SOUL.md + MEMORY.md + LanceDB recall) ───────────────
from klerk.cli import memory_cmd  # noqa: E402

memory_app = typer.Typer(name="memory", help="Long-term memory — SOUL / MEMORY / recall.", no_args_is_help=True)
app.add_typer(memory_app)
memory_app.command("recall", help="Recall durable facts (hybrid vector + BM25 + RRF).")(memory_cmd.recall)
memory_app.command("save", help="Save a durable fact (appends MEMORY.md + embeds).")(memory_cmd.save)
memory_app.command("show-soul", help="Print SOUL.md (seeded with the klerk persona).")(memory_cmd.show_soul)
memory_app.command("edit-soul", help="Open SOUL.md in $EDITOR.")(memory_cmd.edit_soul)


# ─── Q&A and doc-writer verbs ────────────────────────────────────────────────
app.command("ask", help="Q&A over the corpus (CRAG-lite + citations).")(ask_cmd)
app.command("write", help="Adversarial doc-writer (Drafter-A vs Drafter-B + Adjudicator + Critic).")(write_cmd)

# ─── Brief-option verbs (S1 / Phase A.1) ─────────────────────────────────────
# extract-actions = Brief Option B; escalate draft = Brief Option A.
from klerk.cli.extract_actions_cmd import extract_actions_cmd  # noqa: E402
from klerk.cli.escalate_cmd import escalate_draft_cmd  # noqa: E402

app.command("extract-actions", help="Brief Option B — extract action items from a doc or text.")(extract_actions_cmd)

escalate_app = typer.Typer(name="escalate", help="Brief Option A — escalation drafter.", no_args_is_help=True)
app.add_typer(escalate_app)
escalate_app.command("draft", help="Draft an escalation email for a low-confidence question.")(escalate_draft_cmd)


def main() -> None:
    """Entry point exposed via [project.scripts] klerk = ..."""
    os.environ.setdefault("LITELLM_LOG", "WARNING")
    app()


if __name__ == "__main__":
    main()
