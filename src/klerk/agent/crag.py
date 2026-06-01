"""Corrective Retrieval-Augmented Generation (CRAG-lite) loop.

Pipeline (one round, with one corrective re-retrieval if needed):

  1. decompose_query  → 1-4 atomic sub-questions
  2. for each sub-q:
       retrieve top-k chunks (hybrid + rerank)
       judge_grounding → score + missing_aspect
       if score < threshold:
           re-retrieve with a query targeted at missing_aspect
  3. answer with all surviving chunks → cited response

The CRAG re-query is capped at one round per sub-question for cost control;
the design-decisions doc explains why "fixed 1-round budget" beats unbounded
self-critique loops for take-home demos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from klerk.agent.llm_json import ask_json
from klerk.agent.prompts.system import (
    ANSWER_PROMPT,
    DECOMPOSE_PROMPT,
    JUDGE_PROMPT,
    KLERK_SYSTEM,
)
from klerk.agent.schemas import (
    Chunk,
    CitedAnswer,
    DecomposedQuery,
    GroundingJudgment,
)
from klerk.llm.router import complete
from klerk.rag.retrieve import RetrievedChunk, search_hybrid

CITATION_RE = re.compile(r"\[([a-zA-Z0-9_\-]+):(\d+)\]")


@dataclass
class CragTrace:
    """Per-step trace for one ask round, surfaceable in the Studio Trace panel."""

    question: str
    sub_questions: list[str]
    retrievals: list[list[RetrievedChunk]]      # one inner list per sub-q
    judgments: list[GroundingJudgment]
    corrections: list[list[RetrievedChunk] | None]  # parallel; None if no correction
    answer: CitedAnswer


# ─── Tool 1: decompose_query ─────────────────────────────────────────────────
def decompose_query(question: str, *, locale: str = "en") -> DecomposedQuery:
    return ask_json(
        DecomposedQuery,
        system=DECOMPOSE_PROMPT,
        user=question,
        locale=locale,
    )


# ─── Tool 2: judge_grounding ─────────────────────────────────────────────────
def judge_grounding(
    question: str,
    chunks: list[RetrievedChunk] | list[Chunk],
    *,
    locale: str = "en",
) -> GroundingJudgment:
    context = "\n\n".join(
        f"[{c.chunk_id}] {c.text}" for c in chunks
    ) or "(no chunks retrieved)"
    user = f"QUESTION:\n{question}\n\nRETRIEVED CHUNKS:\n{context}"
    return ask_json(
        GroundingJudgment,
        system=JUDGE_PROMPT,
        user=user,
        locale=locale,
        max_tokens=400,
    )


# ─── Answer step ─────────────────────────────────────────────────────────────
def _answer_with_citations(
    question: str,
    chunks: list[RetrievedChunk],
    *,
    locale: str = "en",
) -> CitedAnswer:
    context = "\n\n".join(
        f"[{c.chunk_id}] {c.text}" for c in chunks
    ) or "(no chunks retrieved)"
    messages = [
        {"role": "system", "content": KLERK_SYSTEM + "\n\n" + ANSWER_PROMPT},
        {"role": "user", "content": f"QUESTION:\n{question}\n\nRETRIEVED CHUNKS:\n{context}"},
    ]
    response = complete(messages=messages, locale=locale, temperature=0.0, max_tokens=600)
    text = response.choices[0].message.content or ""
    citations = sorted({f"{m.group(1)}:{m.group(2)}" for m in CITATION_RE.finditer(text)})

    # Confidence reflects how well-grounded the answer is. Crucially, the
    # retrieval-pool size (k_final) is NOT the denominator: citing 2 of 8
    # retrieved chunks is the normal *good* case, not 25% confidence. Scale by
    # the answer's own distinct grounded sources, capped below 1.0 for a single
    # source. An uncited answer (including a correct "I don't know" refusal)
    # gets 0.0, matching the orchestrator path's contract.
    if not chunks or not citations:
        confidence = 0.0
    else:
        distinct_docs = len({c.split(":", 1)[0] for c in citations})
        confidence = min(1.0, 0.7 + 0.15 * distinct_docs)

    return CitedAnswer(answer=text.strip(), citations=citations, confidence=confidence, locale=locale)


# ─── End-to-end ask ──────────────────────────────────────────────────────────
def ask(
    question: str,
    *,
    locale: str = "en",
    k_final: int = 6,
    judge_threshold: float = 0.6,
    correct: bool = True,
) -> CragTrace:
    """One end-to-end CRAG-lite round. Returns CragTrace; surface via Studio."""
    decomposed = decompose_query(question, locale=locale)
    sub_qs = decomposed.sub_questions

    retrievals: list[list[RetrievedChunk]] = []
    judgments: list[GroundingJudgment] = []
    corrections: list[list[RetrievedChunk] | None] = []
    all_chunks: dict[str, RetrievedChunk] = {}

    for sq in sub_qs:
        hits = search_hybrid(sq, k_initial=16, k_final=k_final, rerank=True)
        retrievals.append(hits)
        for h in hits:
            all_chunks.setdefault(h.chunk_id, h)

        if not correct:
            judgments.append(GroundingJudgment(score=1.0, missing_aspect="", rationale="(skipped)"))
            corrections.append(None)
            continue

        verdict = judge_grounding(sq, hits, locale=locale)
        judgments.append(verdict)

        if verdict.score < judge_threshold and verdict.missing_aspect:
            corrective_query = f"{sq} — specifically: {verdict.missing_aspect}"
            new_hits = search_hybrid(corrective_query, k_initial=16, k_final=k_final, rerank=True)
            corrections.append(new_hits)
            for h in new_hits:
                all_chunks.setdefault(h.chunk_id, h)
        else:
            corrections.append(None)

    final_chunks = sorted(all_chunks.values(), key=lambda c: c.score, reverse=True)[: k_final * 2]
    answer = _answer_with_citations(question, final_chunks, locale=locale)

    return CragTrace(
        question=question,
        sub_questions=sub_qs,
        retrievals=retrievals,
        judgments=judgments,
        corrections=corrections,
        answer=answer,
    )
