"""`klerk ask "<question>"` — end-to-end CRAG-lite Q&A with citations."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from klerk.agent.crag import ask as crag_ask
from klerk.cli._agent_flag import agent_console, emit, with_agent_mode

console = agent_console()


@with_agent_mode
def ask_cmd(
    question: Annotated[str, typer.Argument(help="Question to answer over the corpus.")],
    locale: Annotated[str, typer.Option("--locale", "-l", help="en | id")] = "en",
    k: Annotated[int, typer.Option("--k", "-k", help="Final chunks per sub-question.")] = 6,
    no_correct: Annotated[bool, typer.Option("--no-correct", help="Skip the CRAG re-retrieval step.")] = False,
    trace: Annotated[bool, typer.Option("--trace", help="Show decomposition + judgment table.")] = False,
) -> None:
    """Decompose → retrieve → rerank → judge → (correct) → answer + cite."""
    trace_obj = crag_ask(
        question,
        locale=locale,
        k_final=k,
        correct=not no_correct,
    )

    if trace:
        sub_table = Table(title="Sub-questions + grounding", border_style="dim")
        sub_table.add_column("#", justify="right", style="dim")
        sub_table.add_column("sub_question")
        sub_table.add_column("score", justify="right")
        sub_table.add_column("missing_aspect", style="yellow")
        sub_table.add_column("re-tried", justify="center")
        for i, (sq, judg, corr) in enumerate(
            zip(trace_obj.sub_questions, trace_obj.judgments, trace_obj.corrections, strict=False),
            start=1,
        ):
            sub_table.add_row(
                str(i),
                sq,
                f"{judg.score:.2f}",
                judg.missing_aspect or "—",
                "✓" if corr is not None else "—",
            )
        console.print(sub_table)

    console.print(
        Panel(
            trace_obj.answer.answer,
            title=f"Answer (confidence {trace_obj.answer.confidence:.2f}, locale={trace_obj.answer.locale})",
            border_style="green",
        )
    )

    if trace_obj.answer.citations:
        cite_table = Table(title="Citations", border_style="cyan")
        cite_table.add_column("chunk_id", style="cyan")
        cite_table.add_column("doc_id", style="dim")
        cite_table.add_column("preview")
        by_id = {c.chunk_id: c for round_ in trace_obj.retrievals for c in round_}
        for round_ in trace_obj.corrections:
            if round_:
                for c in round_:
                    by_id.setdefault(c.chunk_id, c)
        for cid in trace_obj.answer.citations:
            chunk = by_id.get(cid)
            preview = (chunk.text[:140].replace("\n", " ") + "…") if chunk else "(missing)"
            cite_table.add_row(cid, chunk.doc_id if chunk else "?", preview)
        console.print(cite_table)
    else:
        console.print("[yellow]No citations parsed from the answer.[/yellow]")

    emit(
        {
            "question": question,
            "answer": trace_obj.answer.answer,
            "confidence": trace_obj.answer.confidence,
            "locale": trace_obj.answer.locale,
            "citations": list(trace_obj.answer.citations),
            "sub_questions": list(trace_obj.sub_questions),
        }
    )
