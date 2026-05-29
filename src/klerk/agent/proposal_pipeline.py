"""Adversarial proposal pipeline (Dynamic-Workflows-inspired).

Seven stages, with parallel competing drafters in the middle:

    Researcher  →  Scope  →  ┌── Drafter-A ──┐
                             │               │  →  Citation Tracer
                             └── Drafter-B ──┘
                                      │
                                      ▼
                                 Adjudicator (picks winner)
                                      │
                                      ▼
                                   Critic (5-axis rubric)

The headline 2026-paradigm extract is the parallel A/B drafters + adjudicator.
Drafters write competing sections grounded in the same retrieved chunks; the
adjudicator picks the stronger one; the critic scores the winner against the
klerk custom rubric.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from klerk.agent.llm_json import ask_json
from klerk.agent.prompts.system import (
    ADJUDICATE_PROMPT,
    CRITIC_PROMPT,
    KLERK_SYSTEM,
    PROPOSE_DRAFT_PROMPT,
    PROPOSE_SCOPE_PROMPT,
)
from klerk.agent.schemas import (
    Adjudication,
    DraftedSection,
    ProposalScope,
    ProposalSection,
    RubricScores,
)
from klerk.llm.router import complete
from klerk.rag.retrieve import RetrievedChunk, search_hybrid

CITATION_RE = re.compile(r"\[([a-zA-Z0-9_\-]+):(\d+)\]")


@dataclass
class SectionRound:
    """All the artifacts for one section of the proposal."""

    section: ProposalSection
    retrieved: list[RetrievedChunk]
    draft_a: DraftedSection
    draft_b: DraftedSection
    adjudication: Adjudication
    rubric: RubricScores
    cite_check_a: dict[str, bool] = field(default_factory=dict)  # chunk_id → exists?
    cite_check_b: dict[str, bool] = field(default_factory=dict)

    @property
    def winning_draft(self) -> DraftedSection:
        return self.draft_a if self.adjudication.winner == "A" else self.draft_b


@dataclass
class Proposal:
    """End-to-end output. `to_markdown()` renders the final shippable doc."""

    topic: str
    locale: str
    scope: ProposalScope
    rounds: list[SectionRound]
    summary_rubric: RubricScores | None = None

    def to_markdown(self) -> str:
        out: list[str] = [f"# {self.topic}", ""]
        for r in self.rounds:
            out.append(f"## {r.section.title}")
            out.append("")
            out.append(r.winning_draft.body)
            out.append("")
        if self.summary_rubric:
            out.append("---")
            out.append("")
            out.append("## klerk rubric — average across sections")
            out.append("")
            r = self.summary_rubric
            out.append(f"- faithfulness: **{r.faithfulness:.2f}**")
            out.append(f"- citation_coverage: **{r.citation_coverage:.2f}**")
            out.append(f"- contradiction_freeness: **{r.contradiction_freeness:.2f}**")
            out.append(f"- section_coverage: **{r.section_coverage:.2f}**")
            out.append(f"- tone: **{r.tone:.2f}**")
            out.append(f"- **mean: {r.mean:.2f}**")
            out.append("")
            if r.notes:
                out.append("### critic notes")
                out.extend(f"- {n}" for n in r.notes)
        return "\n".join(out)


# ─── Stage 1: Scope (planner) ────────────────────────────────────────────────
def plan_scope(topic: str, *, n_sections: int = 3, locale: str = "en") -> ProposalScope:
    user = (
        f"TOPIC: {topic}\n"
        f"REQUESTED SECTION COUNT: {n_sections}\n"
        f"LOCALE: {locale}\n"
        "Plan the sections."
    )
    return ask_json(
        ProposalScope,
        system=PROPOSE_SCOPE_PROMPT,
        user=user,
        locale=locale,
        max_tokens=1200,
    )


# ─── Stage 2: Researcher (per section) ───────────────────────────────────────
def gather_evidence(section: ProposalSection, *, k: int = 8) -> list[RetrievedChunk]:
    """Hybrid retrieve over the section's title + bullets + target_chunk hints."""
    query_parts = [section.title, *section.bullets, *section.target_chunks]
    query = " · ".join(p for p in query_parts if p)
    return search_hybrid(query, k_initial=16, k_final=k, rerank=True)


# ─── Stage 3a/3b: Drafter A and Drafter B in parallel ────────────────────────
def _draft_section(
    section: ProposalSection,
    chunks: list[RetrievedChunk],
    *,
    drafter_id: str,
    locale: str,
) -> DraftedSection:
    context = "\n\n".join(f"[{c.chunk_id}] {c.text}" for c in chunks) or "(no evidence)"
    bullets = "\n".join(f"- {b}" for b in section.bullets)
    differentiator = (
        "You are DRAFTER A — favor structured argument and direct quotation."
        if drafter_id == "A"
        else "You are DRAFTER B — favor implication, contextualization, and synthesis across chunks."
    )
    user = (
        f"SECTION TITLE: {section.title}\n"
        f"BULLETS TO COVER:\n{bullets}\n\n"
        f"{differentiator}\n\n"
        f"RETRIEVED EVIDENCE:\n{context}"
    )
    messages = [
        {"role": "system", "content": KLERK_SYSTEM + "\n\n" + PROPOSE_DRAFT_PROMPT},
        {"role": "user", "content": user},
    ]
    response = complete(messages=messages, locale=locale, temperature=0.2, max_tokens=900)
    body = (response.choices[0].message.content or "").strip()
    citations = sorted({f"{m.group(1)}:{m.group(2)}" for m in CITATION_RE.finditer(body)})
    return DraftedSection(
        section_title=section.title,
        drafter_id=drafter_id,  # type: ignore[arg-type]
        body=body,
        citations=citations,
    )


def draft_competing(
    section: ProposalSection,
    chunks: list[RetrievedChunk],
    *,
    locale: str = "en",
) -> tuple[DraftedSection, DraftedSection]:
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_a = ex.submit(_draft_section, section, chunks, drafter_id="A", locale=locale)
        fut_b = ex.submit(_draft_section, section, chunks, drafter_id="B", locale=locale)
        return fut_a.result(), fut_b.result()


# ─── Stage 4: Citation tracer ────────────────────────────────────────────────
def trace_citations(draft: DraftedSection, chunks: list[RetrievedChunk]) -> dict[str, bool]:
    """Verify every cited chunk_id was actually in the retrieved set.

    Returns `{chunk_id: present}`. Hallucinated citations (id ∉ retrieved set)
    map to False; the adjudicator + critic see these and penalize accordingly.
    """
    available = {c.chunk_id for c in chunks}
    return {cid: cid in available for cid in draft.citations}


# ─── Stage 5: Adjudicator ────────────────────────────────────────────────────
def adjudicate(
    section: ProposalSection,
    draft_a: DraftedSection,
    draft_b: DraftedSection,
    *,
    locale: str = "en",
) -> Adjudication:
    user = (
        f"SECTION: {section.title}\n"
        f"BULLETS: {section.bullets}\n\n"
        f"=== DRAFT A ===\n{draft_a.body}\n\n"
        f"=== DRAFT B ===\n{draft_b.body}\n\n"
        "Pick the winner."
    )
    return ask_json(
        Adjudication,
        system=ADJUDICATE_PROMPT,
        user=user,
        locale=locale,
        max_tokens=600,
    )


# ─── Stage 6: Critic (rubric) ────────────────────────────────────────────────
def score_rubric(
    section: ProposalSection,
    winning: DraftedSection,
    chunks: list[RetrievedChunk],
    cite_check: dict[str, bool],
    *,
    locale: str = "en",
) -> RubricScores:
    bullets = "\n".join(f"- {b}" for b in section.bullets)
    context = "\n\n".join(f"[{c.chunk_id}] {c.text}" for c in chunks) or "(none)"
    hallucinated = [cid for cid, ok in cite_check.items() if not ok]
    user = (
        f"SECTION: {section.title}\n"
        f"BULLETS TO COVER:\n{bullets}\n\n"
        f"WINNING DRAFT:\n{winning.body}\n\n"
        f"EVIDENCE AVAILABLE:\n{context}\n\n"
        f"HALLUCINATED CITATIONS (none = good): {hallucinated or 'none'}\n"
    )
    return ask_json(
        RubricScores,
        system=CRITIC_PROMPT,
        user=user,
        locale=locale,
        max_tokens=600,
    )


# ─── End-to-end orchestration ────────────────────────────────────────────────
def propose(
    topic: str,
    *,
    n_sections: int = 3,
    k_per_section: int = 8,
    locale: str = "en",
) -> Proposal:
    """One end-to-end proposal run. Returns the assembled Proposal."""
    scope = plan_scope(topic, n_sections=n_sections, locale=locale)

    rounds: list[SectionRound] = []
    for section in scope.sections:
        chunks = gather_evidence(section, k=k_per_section)
        draft_a, draft_b = draft_competing(section, chunks, locale=locale)
        cite_a = trace_citations(draft_a, chunks)
        cite_b = trace_citations(draft_b, chunks)
        adj = adjudicate(section, draft_a, draft_b, locale=locale)
        winning = draft_a if adj.winner == "A" else draft_b
        cite_check = cite_a if adj.winner == "A" else cite_b
        rubric = score_rubric(section, winning, chunks, cite_check, locale=locale)
        rounds.append(
            SectionRound(
                section=section,
                retrieved=chunks,
                draft_a=draft_a,
                draft_b=draft_b,
                adjudication=adj,
                rubric=rubric,
                cite_check_a=cite_a,
                cite_check_b=cite_b,
            )
        )

    # Section-mean rubric for the summary footer
    if rounds:
        avg = RubricScores(
            faithfulness=sum(r.rubric.faithfulness for r in rounds) / len(rounds),
            citation_coverage=sum(r.rubric.citation_coverage for r in rounds) / len(rounds),
            contradiction_freeness=sum(r.rubric.contradiction_freeness for r in rounds) / len(rounds),
            section_coverage=sum(r.rubric.section_coverage for r in rounds) / len(rounds),
            tone=sum(r.rubric.tone for r in rounds) / len(rounds),
            notes=[n for r in rounds for n in r.rubric.notes][:6],
        )
    else:
        avg = None

    return Proposal(topic=topic, locale=locale, scope=scope, rounds=rounds, summary_rubric=avg)


def save_proposal(p: Proposal, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or Path("data/output/proposals")
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\-]+", "_", p.topic.lower()).strip("_")[:60]
    path = out_dir / f"{slug}.md"
    path.write_text(p.to_markdown(), encoding="utf-8")
    return path
