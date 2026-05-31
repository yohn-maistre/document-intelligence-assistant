"""Pydantic output schemas for klerk's agentic capabilities.

One file so the schemas stay aligned across the agent, the FastAPI public
surface, and the agentskills.io manifests (step 8). Each model carries
just enough structure for downstream consumers (Studio panels, email
clients, calendar systems) to do something useful without further parsing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ─── A · Escalation Drafter ──────────────────────────────────────────────────
class EscalationDraft(BaseModel):
    """A draft email asking a human to step in. Surfaced when /chat hits a
    low-confidence / out-of-corpus situation."""

    to: list[str] = Field(..., description="Email addresses or role names.")
    cc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    urgency: Literal["low", "medium", "high"] = "medium"
    rationale: str = Field(..., description="Why klerk thinks a human is needed.")
    source_question: str
    confidence_observed: float = Field(..., ge=0.0, le=1.0)


# ─── B · Action Item Extractor ───────────────────────────────────────────────
class ActionItem(BaseModel):
    """One actionable bullet pulled out of a doc or text snippet."""

    assignee: str = Field(..., description="Person, role, or team named as owner.")
    action: str = Field(..., description="What needs to happen.")
    due: str | None = Field(default=None, description="Date / deadline if stated.")
    priority: Literal["low", "medium", "high"] = "medium"
    source_chunk: str | None = Field(
        default=None, description="chunk_id of the citation; null if from raw text."
    )


class ActionExtraction(BaseModel):
    items: list[ActionItem]
    source: str = Field(..., description="`doc:<doc_id>` or `text` depending on input.")


# ─── D · Writer (multi-drafter adversarial doc-writer) ───────────────────────
# The actual orchestration is in klerk.agent.doc_writer; this model is
# the clean public output. The full Proposal object (with per-draft trace, the
# adjudication reasoning, and the citation-check matrix) stays internal.
class WriterSection(BaseModel):
    title: str
    body: str
    winner: Literal["A", "B"]
    citations: list[str]


class WriterDraftSummary(BaseModel):
    topic: str
    locale: str
    sections: list[WriterSection]
    rubric_mean: float | None = None
    n_drafts_per_section: int = 2  # A/B
    generated_at: datetime


# ─── E · Drift agent ─────────────────────────────────────────────────────────
DriftType = Literal[
    "doc_added",
    "doc_changed",
    "doc_removed",
    "scope_drift",      # semantic shift detected by chunk-embedding centroid
    "tone_drift",       # large sentiment / formality delta
]


class DriftEvent(BaseModel):
    type: DriftType
    doc_id: str
    timestamp: datetime
    summary: str = Field(..., description="One-sentence English description of the change.")
    before_excerpt: str | None = Field(default=None, description="Snippet from the prior corpus.")
    after_excerpt: str | None = Field(default=None, description="Snippet from the current corpus.")


class DriftScanReport(BaseModel):
    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    n_docs_scanned: int = 0
    events: list[DriftEvent] = Field(default_factory=list)
    error: str | None = None
