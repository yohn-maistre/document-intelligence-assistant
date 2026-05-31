"""`klerk escalate draft` — Brief Option A (Escalation Drafter).

Thin CLI wrapper over :func:`klerk.agent.escalation.draft`. When retrieval can't
answer a question with confidence, klerk drafts an escalation email to the right
human instead of bluffing. The caller supplies the observed confidence (the
chat loop derives this from the CRAG judge / rerank threshold); here it is a
flag so operators can exercise the path directly.

Output is the structured ``EscalationDraft`` — ``{to, cc, subject, body, ...}``,
directly serialisable to an email client / Slack / ticket payload.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from klerk.agent.escalation import draft
from klerk.cli._agent_flag import agent_console, emit, with_agent_mode

console = agent_console()


@with_agent_mode
def escalate_draft_cmd(
    question: Annotated[str, typer.Argument(help="The user question klerk could not answer.")],
    confidence: Annotated[
        float,
        typer.Option("--confidence", "-c", min=0.0, max=1.0, help="Observed retrieval confidence."),
    ] = 0.0,
    excerpt: Annotated[
        str,
        typer.Option("--excerpt", help="What klerk did find (may be irrelevant)."),
    ] = "",
    locale: Annotated[str, typer.Option("--locale", "-l", help="en | id")] = "en",
) -> None:
    """Draft an escalation email asking the right human to step in."""
    try:
        result = draft(
            question=question,
            confidence=confidence,
            retrieved_excerpt=excerpt,
            locale=locale,
        )
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    meta = Table(show_header=False, border_style="dim")
    meta.add_column("key", style="dim")
    meta.add_column("value")
    meta.add_row("to", ", ".join(result.to))
    meta.add_row("cc", ", ".join(result.cc) or "—")
    meta.add_row("subject", result.subject)
    meta.add_row("urgency", result.urgency)
    meta.add_row("confidence_observed", f"{result.confidence_observed:.2f}")
    console.print(meta)
    console.print(Panel(result.body, title="Body", border_style="yellow"))
    console.print(f"[dim]rationale: {result.rationale}[/dim]")

    emit(result.model_dump())
