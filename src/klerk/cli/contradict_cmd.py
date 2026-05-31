"""`klerk contradict scan` — pairwise contradiction sweep over the KG."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from klerk.agent.contradiction import save_report, scan
from klerk.cli._agent_flag import agent_console, emit, with_agent_mode

console = agent_console()


def _findings_payload(findings) -> list[dict]:
    return [
        {
            "relation": verdict.entity_or_relation,
            "consistent": verdict.consistent,
            "contradiction": verdict.contradiction,
            "evidence_chunks": list(grp.evidence_chunks),
        }
        for grp, verdict in findings
    ]


@with_agent_mode
def scan_cmd(
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en",
) -> None:
    """Group KG edges by (source, target, verb-stem), then LLM-judge consistency."""
    try:
        findings = scan(locale=locale)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    if not findings:
        console.print(Panel("No contradictions detected.", border_style="green"))
        path = save_report(findings)
        console.print(f"[dim]report: {path}[/dim]")
        emit({"n_findings": 0, "report": str(path), "findings": []})
        return

    table = Table(title=f"{len(findings)} potential contradiction(s)", border_style="yellow")
    table.add_column("relation", style="cyan")
    table.add_column("status", justify="center")
    table.add_column("contradiction", style="yellow")
    table.add_column("chunks", style="dim")
    for grp, verdict in findings:
        table.add_row(
            verdict.entity_or_relation,
            "[red]INCONSISTENT[/red]" if not verdict.consistent else "flagged",
            verdict.contradiction or "(no detail)",
            ", ".join(grp.evidence_chunks),
        )
    console.print(table)

    path = save_report(findings)
    console.print(f"\n[green]✓[/green] Report written: [cyan]{path}[/cyan]")
    emit(
        {
            "n_findings": len(findings),
            "report": str(path),
            "findings": _findings_payload(findings),
        }
    )
