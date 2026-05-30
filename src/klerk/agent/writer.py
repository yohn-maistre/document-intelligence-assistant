"""Capability D — Writer (multi-drafter adversarial doc-writer).

Thin façade over `klerk.agent.doc_writer` that maps the internal `Proposal`
dataclass to the public `WriterDraftSummary` Pydantic model. The actual A/B
drafting + adjudication + 5-axis critic logic stays in doc_writer (arranged
as a LangGraph spine in doc_writer_graph); this module exists so the FastAPI
surface, the Studio "Drafts" panel, and the skill manifest all reach the
writer through one stable signature.
"""

from __future__ import annotations

from datetime import datetime, timezone

from klerk.agent._models import WriterDraftSummary, WriterSection
from klerk.agent.doc_writer import Proposal, propose


def _to_public(proposal: Proposal) -> WriterDraftSummary:
    sections = [
        WriterSection(
            title=r.section.title,
            body=r.winning_draft.body,
            winner=r.adjudication.winner,
            citations=list(r.winning_draft.citations),
        )
        for r in proposal.rounds
    ]
    return WriterDraftSummary(
        topic=proposal.topic,
        locale=proposal.locale,
        sections=sections,
        rubric_mean=proposal.summary_rubric.mean if proposal.summary_rubric else None,
        generated_at=datetime.now(timezone.utc),
    )


def write_draft(
    topic: str,
    *,
    n_sections: int = 3,
    k_per_section: int = 8,
    locale: str = "en",
) -> WriterDraftSummary:
    """Run the full multi-drafter pipeline for `topic` and return the
    public summary. Use the internal `propose()` directly if you need the
    full per-section trace (drafter-A vs drafter-B bodies, the
    adjudication reasoning, the citation-check matrix)."""
    proposal = propose(
        topic,
        n_sections=n_sections,
        k_per_section=k_per_section,
        locale=locale,
    )
    return _to_public(proposal)


# Backwards-compat alias: matches the FastAPI route's expected import shape.
draft = write_draft
