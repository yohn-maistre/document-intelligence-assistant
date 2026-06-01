"""`klerk eval run` — RAGAS + klerk's custom 5-axis rubric.

SEA-HELM-style Bahasa parity reporting was demoted in the v5 cleanup pass;
the brief's 2-Bahasa-Q evaluation is exercised through the standard rubric.
See `experimental/README.md`.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from klerk.cli._agent_flag import agent_console, emit, with_agent_mode
from klerk.eval import ragas_runner, rubric
from klerk.eval.golden import load as load_golden
from klerk.llm.cache import cache_stats

console = agent_console()


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str, indent=2, ensure_ascii=False))
    return path


def _render_axis_table(name: str, summary: dict) -> Table:
    t = Table(title=name, border_style="green")
    t.add_column("axis")
    t.add_column("score", justify="right")
    for axis in (
        "retrieval_recall",
        "substring_coverage",
        "citation_grounded",
        "locale_match",
        "confidence",
        "mean",
    ):
        if axis in summary:
            colour = "green" if summary[axis] >= 0.8 else "yellow" if summary[axis] >= 0.5 else "red"
            t.add_row(axis, f"[{colour}]{summary[axis]:.2f}[/{colour}]")
    return t


@with_agent_mode
def run_cmd(
    locale: Annotated[str | None, typer.Option("--locale", "-l", help="Restrict to one locale (en | id).")] = None,
    do_ragas: Annotated[bool, typer.Option("--ragas/--no-ragas", help="Run RAGAS baseline.")] = True,
    do_rubric: Annotated[bool, typer.Option("--rubric/--no-rubric", help="Run klerk's custom 5-axis rubric.")] = True,
    out_dir: Annotated[Path, typer.Option("--out", help="Where to dump JSON reports.")] = Path("data/output/eval"),
) -> None:
    """Run the eval suite. Each metric writes its own JSON file under --out."""
    items = load_golden(locale=locale)
    if not items:
        console.print(f"[red]No golden items found for locale={locale or 'any'}. "
                      f"Drop YAML files into data/golden/.[/red]")
        raise typer.Exit(code=1)

    console.print(Panel.fit(
        f"[bold cyan]klerk eval run[/bold cyan]  ·  {len(items)} golden item(s)\n"
        f"[dim]ragas={do_ragas}  rubric={do_rubric}  locale={locale or 'all'}[/dim]",
        border_style="cyan",
    ))

    payload: dict = {"n_items": len(items), "locale": locale or "all"}

    # ── Custom 5-axis rubric ──────────────────────────────────────────────
    if do_rubric:
        console.print(Rule("[bold]klerk 5-axis rubric[/bold]", style="green"))
        results = rubric.run(items)
        agg = rubric.aggregate(results)
        # Headline is the brief's in-scope 20; the out-of-corpus stretch set
        # (e.g. Japanese) is reported separately so it never silently drags it.
        if agg.get("brief"):
            console.print(_render_axis_table("Brief set (in scope)", agg["brief"]))
        if agg.get("stretch"):
            console.print(_render_axis_table(
                "Stretch set (out of corpus — source docs not ingested)", agg["stretch"]))
        if agg["by_locale"]:
            for loc, summary in agg["by_locale"].items():
                console.print(_render_axis_table(f"locale = {loc}", summary))
        path = _write_json(out_dir / "rubric.json", {
            "items": [asdict(r) for r in results],
            "aggregate": agg,
        })
        console.print(f"[dim]→ {path}[/dim]\n")
        payload["rubric"] = {"aggregate": agg, "report": str(path)}

    # ── RAGAS baseline ────────────────────────────────────────────────────
    if do_ragas:
        console.print(Rule("[bold]RAGAS baseline[/bold]", style="green"))
        report = ragas_runner.run(items)
        if not report.available:
            console.print(f"[yellow]RAGAS skipped: {report.reason}[/yellow]")
        elif report.reason:
            console.print(f"[yellow]RAGAS partial: {report.reason}[/yellow]")
        else:
            t = Table(title="RAGAS aggregate", border_style="green")
            t.add_column("metric")
            t.add_column("score", justify="right")
            for k, v in report.aggregate.items():
                colour = "green" if v >= 0.8 else "yellow" if v >= 0.5 else "red"
                t.add_row(k, f"[{colour}]{v:.2f}[/{colour}]")
            console.print(t)
        path = _write_json(out_dir / "ragas.json", {
            "available": report.available,
            "reason": report.reason,
            "items": [asdict(it) for it in report.items],
            "aggregate": report.aggregate,
        })
        console.print(f"[dim]→ {path}[/dim]\n")
        payload["ragas"] = {
            "available": report.available,
            "reason": report.reason,
            "aggregate": report.aggregate,
            "report": str(path),
        }

    # ── Cache footer ──────────────────────────────────────────────────────
    cs = cache_stats()
    console.print(Panel(
        f"disk_entries={cs['disk_entries']}  semantic_entries={cs['semantic_entries']}  "
        f"semantic={'on' if cs['semantic_enabled'] else 'off'} (thr={cs['semantic_threshold']})",
        title="cache state after eval",
        border_style="dim",
    ))
    emit(payload)
