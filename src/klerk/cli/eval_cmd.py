"""`klerk eval run` — RAGAS + custom 5-axis rubric + SEA-HELM Bahasa parity."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from klerk.eval import ragas_runner, rubric, seahelm_runner
from klerk.eval.golden import load as load_golden
from klerk.llm.cache import cache_stats

console = Console()


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


def run_cmd(
    locale: Annotated[str | None, typer.Option("--locale", "-l", help="Restrict to one locale (en | id).")] = None,
    do_ragas: Annotated[bool, typer.Option("--ragas/--no-ragas", help="Run RAGAS baseline.")] = True,
    do_rubric: Annotated[bool, typer.Option("--rubric/--no-rubric", help="Run klerk's custom 5-axis rubric.")] = True,
    do_seahelm: Annotated[bool, typer.Option("--seahelm/--no-seahelm", help="Run SEA-HELM-style Bahasa parity report.")] = True,
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
        f"[dim]ragas={do_ragas}  rubric={do_rubric}  seahelm={do_seahelm}  locale={locale or 'all'}[/dim]",
        border_style="cyan",
    ))

    # ── Custom 5-axis rubric ──────────────────────────────────────────────
    if do_rubric:
        console.print(Rule("[bold]klerk 5-axis rubric[/bold]", style="green"))
        results = rubric.run(items)
        agg = rubric.aggregate(results)
        console.print(_render_axis_table("Overall (all items)", agg["overall"]))
        if agg["by_locale"]:
            for loc, summary in agg["by_locale"].items():
                console.print(_render_axis_table(f"locale = {loc}", summary))
        path = _write_json(out_dir / "rubric.json", {
            "items": [asdict(r) for r in results],
            "aggregate": agg,
        })
        console.print(f"[dim]→ {path}[/dim]\n")

    # ── SEA-HELM-style Bahasa parity ──────────────────────────────────────
    if do_seahelm:
        console.print(Rule("[bold]SEA-HELM-style Bahasa parity[/bold]", style="green"))
        sh = seahelm_runner.run_seahelm()
        if sh.get("available") and sh.get("id_minus_en_delta"):
            delta = sh["id_minus_en_delta"]
            t = Table(title="Δ = Bahasa score − English score", border_style="cyan")
            t.add_column("axis")
            t.add_column("delta", justify="right")
            for axis, d in delta.items():
                colour = "green" if abs(d) < 0.1 else "yellow" if abs(d) < 0.25 else "red"
                t.add_row(axis, f"[{colour}]{d:+.2f}[/{colour}]")
            console.print(t)
        else:
            console.print("[yellow]SEA-HELM: insufficient golden items (need both en and id).[/yellow]")
        path = _write_json(out_dir / "seahelm.json", {
            "aggregate": sh.get("aggregate", {}),
            "id_minus_en_delta": sh.get("id_minus_en_delta", {}),
        })
        console.print(f"[dim]→ {path}[/dim]\n")

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

    # ── Cache footer ──────────────────────────────────────────────────────
    cs = cache_stats()
    console.print(Panel(
        f"disk_entries={cs['disk_entries']}  semantic_entries={cs['semantic_entries']}  "
        f"semantic={'on' if cs['semantic_enabled'] else 'off'} (thr={cs['semantic_threshold']})",
        title="cache state after eval",
        border_style="dim",
    ))
