"""`klerk write "<topic>"` — adversarial multi-drafter doc-writer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from klerk.agent.doc_writer import propose, save_proposal
from klerk.cli._agent_flag import agent_console, emit, with_agent_mode

console = agent_console()


@with_agent_mode
def write_cmd(
    topic: Annotated[str, typer.Argument(help="Document topic.")],
    sections: Annotated[int, typer.Option("--sections", "-n", help="Number of sections.")] = 3,
    k: Annotated[int, typer.Option("--k", "-k", help="Evidence chunks per section.")] = 8,
    locale: Annotated[str, typer.Option("--locale", "-l")] = "en",
    out_dir: Annotated[Path, typer.Option("--out", help="Output dir for the .md file.")] = Path("data/output/proposals"),
    run_id: Annotated[str | None, typer.Option("--run-id", help="Stable run id for checkpoint/resume.")] = None,
    resume: Annotated[bool, typer.Option("--resume", help="Return the checkpointed doc for --run-id instead of re-running.")] = False,
) -> None:
    """Researcher → Scope → Drafter-A‖Drafter-B → Citation Tracer → Adjudicator → Critic."""
    if resume and not run_id:
        console.print("[red]--resume requires --run-id[/red]")
        raise typer.Exit(code=1)
    console.print(
        Panel.fit(
            f"[bold cyan]klerk write[/bold cyan]: {topic}\n"
            f"[dim]sections={sections}  k={k}  locale={locale}"
            f"{'  (resume ' + run_id + ')' if resume else ''}[/dim]",
            border_style="cyan",
        )
    )

    proposal = propose(
        topic, n_sections=sections, k_per_section=k, locale=locale,
        run_id=run_id, resume=resume,
    )

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
    console.print(f"\n[green]✓[/green] Document written: [cyan]{path}[/cyan]")

    emit(
        {
            "topic": topic,
            "locale": locale,
            "sections": sections,
            "path": str(path),
            "rounds": [
                {
                    "title": r.section.title,
                    "winner": r.adjudication.winner,
                    "rubric_mean": r.rubric.mean,
                }
                for r in proposal.rounds
            ],
            "summary_rubric_mean": (
                proposal.summary_rubric.mean if proposal.summary_rubric else None
            ),
        }
    )
