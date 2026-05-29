"""`klerk propose "<topic>"` — adversarial proposal pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from klerk.agent.proposal_pipeline import propose, save_proposal

console = Console()


def propose_cmd(
    topic: Annotated[str, typer.Argument(help="Proposal topic.")],
    sections: Annotated[int, typer.Option("--sections", "-n", help="Number of sections.")] = 3,
    k: Annotated[int, typer.Option("--k", "-k", help="Evidence chunks per section.")] = 8,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en",
    out_dir: Annotated[Path, typer.Option("--out", help="Output dir for the .md file.")] = Path("data/output/proposals"),
) -> None:
    """Researcher → Scope → Drafter-A‖Drafter-B → Citation Tracer → Adjudicator → Critic."""
    console.print(
        Panel.fit(
            f"[bold cyan]klerk propose[/bold cyan]: {topic}\n"
            f"[dim]sections={sections}  k={k}  locale={locale}[/dim]",
            border_style="cyan",
        )
    )

    proposal = propose(topic, n_sections=sections, k_per_section=k, locale=locale)

    console.print(Rule("[bold]Adjudication summary[/bold]", style="dim"))
    table = Table(border_style="dim")
    table.add_column("§")
    table.add_column("section")
    table.add_column("winner", justify="center")
    table.add_column("rubric mean", justify="right")
    table.add_column("hallucinated cites", justify="right")
    for i, r in enumerate(proposal.rounds, 1):
        cite_check = r.cite_check_a if r.adjudication.winner == "A" else r.cite_check_b
        hallucinated = sum(1 for ok in cite_check.values() if not ok)
        table.add_row(
            str(i),
            r.section.title,
            r.adjudication.winner,
            f"{r.rubric.mean:.2f}",
            f"[red]{hallucinated}[/red]" if hallucinated else "0",
        )
    console.print(table)

    if proposal.summary_rubric:
        sr = proposal.summary_rubric
        console.print(
            Panel(
                f"faithfulness={sr.faithfulness:.2f}  "
                f"citation_cov={sr.citation_coverage:.2f}  "
                f"contradiction_free={sr.contradiction_freeness:.2f}  "
                f"section_cov={sr.section_coverage:.2f}  "
                f"tone={sr.tone:.2f}\n"
                f"[bold]mean: {sr.mean:.2f}[/bold]",
                title="Summary rubric (mean across sections)",
                border_style="green",
            )
        )

    path = save_proposal(proposal, out_dir=out_dir)
    console.print(f"\n[green]✓[/green] Proposal written: [cyan]{path}[/cyan]")
