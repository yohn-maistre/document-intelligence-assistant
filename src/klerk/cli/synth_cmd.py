"""`klerk synth` — Fata Organa synthetic corpus generation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from klerk.synth.specs import CORPUS, constraint_check

console = Console()


def gen_cmd(
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output directory for the generated docs."),
    ] = Path("data/synth/fata_organa"),
    force: Annotated[
        bool, typer.Option("--force", help="Regenerate files that already exist.")
    ] = False,
) -> None:
    """Generate the full 28-doc Fata Organa Solusi corpus."""
    from klerk.synth.gen import generate_one

    # Sanity gate: confirm the corpus plan still satisfies the brief.
    checks = constraint_check()
    failed = [k for k, v in checks.items() if isinstance(v, bool) and not v]
    if failed:
        console.print(
            Panel(
                f"[red]Corpus plan fails brief constraints: {failed}[/red]\n"
                f"[dim]Fix klerk.synth.specs.CORPUS before generating.[/dim]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    out.mkdir(parents=True, exist_ok=True)
    n_generated = 0
    n_cached = 0
    n_failed = 0
    failures: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as prog:
        task = prog.add_task(f"Generating {len(CORPUS)} docs...", total=len(CORPUS))
        for spec in CORPUS:
            target = out / f"{spec.doc_id}.{spec.format}"
            prog.update(task, description=f"[cyan]{spec.doc_id}[/cyan]")
            if not force and target.exists():
                n_cached += 1
                prog.advance(task)
                continue
            try:
                generate_one(spec, out)
                n_generated += 1
            except Exception as e:  # noqa: BLE001
                n_failed += 1
                failures.append((spec.doc_id, f"{type(e).__name__}: {e}"))
            prog.advance(task)

    summary = Table(title="Corpus generation summary", border_style="green", show_header=False)
    summary.add_column("key", style="dim")
    summary.add_column("value")
    summary.add_row("output_dir", str(out))
    summary.add_row("total_specs", str(len(CORPUS)))
    summary.add_row("generated", str(n_generated))
    summary.add_row("cached (skipped)", str(n_cached))
    summary.add_row("[red]failed[/red]", str(n_failed))
    console.print(summary)

    if failures:
        for doc_id, err in failures:
            console.print(f"[red]✗[/red] {doc_id}: {err}")
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[green]✓ Corpus ready.[/green]\n"
            f"Next: [cyan]klerk index build --src {out} --rebuild[/cyan]",
            border_style="green",
        )
    )


def check_cmd() -> None:
    """Verify the corpus PLAN (not output) satisfies every brief constraint."""
    results = constraint_check()
    table = Table(title="Brief-constraint check", border_style="cyan")
    table.add_column("constraint")
    table.add_column("value", justify="right")
    table.add_column("status", justify="center")

    constraints_order = [
        ("total_in_range", f"{results['n_total']} (need 25-30)"),
        ("hr_min_8", f"{results['n_hr']}"),
        ("sop_min_6", f"{results['n_sop']}"),
        ("minutes_min_6", f"{results['n_minutes']}"),
        ("faq_min_4", f"{results['n_faq']}"),
        ("org_min_2", f"{results['n_org']}"),
        ("pdf_min_10", f"{results['n_pdf']}"),
        ("docx_min_10", f"{results['n_docx']}"),
        ("bahasa_min_3", f"{results['n_bahasa']}"),
        ("table_min_2", f"{results['n_with_table']}"),
        ("contradicting_pairs_min_2", f"{results['n_contradiction_docs']} docs ({results['n_contradiction_docs'] // 2} pairs)"),
        ("cross_ref_min_1", f"{results['n_with_cross_refs']}"),
    ]
    all_pass = True
    for name, value in constraints_order:
        ok = results[name]
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        if not ok:
            all_pass = False
        table.add_row(name, value, mark)
    console.print(table)
    if not all_pass:
        raise typer.Exit(code=1)
