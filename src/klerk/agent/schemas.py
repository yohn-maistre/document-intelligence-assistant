"""Pydantic schemas for the tool surface — single source of truth.

Every tool's input and output is a Pydantic model. This gives us:
  - JSON schemas for the MCP server and Pi extension descriptors (free)
  - Runtime validation on every call
  - Structured outputs via Pydantic AI (no fragile JSON-mode parsing)
  - Stable contracts when we refactor the implementation
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─── Retrieval ───────────────────────────────────────────────────────────────
class Chunk(BaseModel):
    """A retrieved chunk — the citable unit."""

    chunk_id: str = Field(description="Stable id, format `<doc_id>:<chunk_idx>`.")
    doc_id: str
    text: str
    locale: str
    source: str
    score: float = Field(description="Fused or rerank score; higher = more relevant.")
    bm25_rank: int = 0
    vector_rank: int = 0
    reranked: bool = False
    rerank_score: float | None = None


# ─── Decomposition ───────────────────────────────────────────────────────────
class DecomposedQuery(BaseModel):
    """Output of `decompose_query` — one to four atomic sub-questions."""

    sub_questions: list[str] = Field(min_length=1, max_length=4)


# ─── Grounding judge ─────────────────────────────────────────────────────────
class GroundingJudgment(BaseModel):
    """Output of `judge_grounding` — does the evidence cover the question?"""

    score: float = Field(ge=0.0, le=1.0)
    missing_aspect: str = Field(default="", description="What's missing if score < 0.6.")
    rationale: str = Field(default="")


# ─── Answer ──────────────────────────────────────────────────────────────────
class CitedAnswer(BaseModel):
    """Output of the answer step — answer text + citations."""

    answer: str
    citations: list[str] = Field(
        default_factory=list,
        description="chunk_ids referenced in the answer (extracted from `[doc:chunk]` markers).",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    locale: str = Field(default="und")


# ─── Knowledge graph ─────────────────────────────────────────────────────────
class Entity(BaseModel):
    id: str = Field(description="Canonical snake-case id, e.g. `acme_corp`.")
    type: Literal[
        "person",
        "organization",
        "policy",
        "contract",
        "date",
        "money",
        "identifier",
        "location",
        "concept",
        "other",
    ]
    name: str
    aliases: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    source: str = Field(description="Source entity id.")
    target: str = Field(description="Target entity id.")
    verb: str = Field(description="Short verb-phrase: `caps_at`, `signed_with`, etc.")
    evidence_chunk: str | None = Field(
        default=None, description="chunk_id supporting this relation."
    )


class ExtractedGraph(BaseModel):
    """Output of `extract_kg` for one chunk."""

    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


# ─── Proposal pipeline ───────────────────────────────────────────────────────
class ProposalSection(BaseModel):
    title: str
    bullets: list[str] = Field(min_length=1, max_length=6)
    target_chunks: list[str] = Field(
        default_factory=list, description="Hints for retrieval keywords/topics."
    )


class ProposalScope(BaseModel):
    """Output of the Scope agent — the section plan."""

    sections: list[ProposalSection] = Field(min_length=1, max_length=8)


class DraftedSection(BaseModel):
    """One drafter's section."""

    section_title: str
    drafter_id: Literal["A", "B"]
    body: str
    citations: list[str] = Field(default_factory=list)


class Adjudication(BaseModel):
    """Output of the Adjudicator — which drafter won, and why."""

    winner: Literal["A", "B"]
    reasons: list[str] = Field(min_length=1, max_length=4)
    improvement_for_winner: str = ""


class RubricScores(BaseModel):
    """5-axis custom rubric — every axis in [0, 1]."""

    faithfulness: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    contradiction_freeness: float = Field(ge=0.0, le=1.0)
    section_coverage: float = Field(ge=0.0, le=1.0)
    tone: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)

    @property
    def mean(self) -> float:
        return (
            self.faithfulness
            + self.citation_coverage
            + self.contradiction_freeness
            + self.section_coverage
            + self.tone
        ) / 5.0


# ─── Contradiction ───────────────────────────────────────────────────────────
class ContradictionFinding(BaseModel):
    """One pairwise contradiction across the KG."""

    consistent: bool
    contradiction: str = ""
    involved_chunks: list[str] = Field(default_factory=list)
    entity_or_relation: str = Field(
        default="", description="Subject of the disagreement (entity id or relation key)."
    )
