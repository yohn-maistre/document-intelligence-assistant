"""Pydantic request/response models for the klerk HTTP API.

These are the public contract. Internal types (CragTrace, Proposal,
ContradictionFinding, etc.) are mapped to these at the route boundary so
internal refactors don't break clients.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ─── Health ──────────────────────────────────────────────────────────────────
class HealthChecks(BaseModel):
    """Per-subsystem readiness snapshot."""

    nemotron_proxy: Literal["ready", "unconfigured"] = "unconfigured"
    lancedb: Literal["ready", "empty", "error"] = "error"
    bge_m3: Literal["loaded", "lazy", "error"] = "lazy"
    drive: Literal["configured", "unconfigured"] = "unconfigured"


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    checks: HealthChecks


# ─── Chat ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    locale: Literal["en", "id"] = "en"
    k: int = Field(default=6, ge=1, le=20, description="Number of chunks to ground on.")


# Chat responses are SSE event streams. Event shapes (informational; not
# enforced by Pydantic since SSE is text/event-stream):
#   event: token       data: {"text": "..."}
#   event: citations   data: {"citations": ["doc:0", ...], "confidence": 0.87}
#   event: done        data: {"ttft_ms": 412, "total_ms": 3104, "cached": false}
#   event: error       data: {"detail": "..."}


# ─── Ingest ──────────────────────────────────────────────────────────────────
class IngestRequest(BaseModel):
    source: Literal["drive", "path"] = "drive"
    path: str | None = Field(default=None, description="Local dir; required if source=path.")
    folder_id: str | None = Field(default=None, description="Override DRIVE_FOLDER_ID env.")

    @model_validator(mode="after")
    def _check_path(self) -> IngestRequest:
        if self.source == "path" and not self.path:
            raise ValueError("source='path' requires `path`")
        return self


class IngestResponse(BaseModel):
    run_id: str
    status: Literal["queued"]
    accepted_at: datetime


class IngestRunStatus(BaseModel):
    run_id: str
    source: Literal["drive", "path"]
    state: Literal["queued", "running", "complete", "failed"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    n_files: int = 0
    n_chunks: int = 0
    error: str | None = None


# ─── Sync status (Drive-specific; mirrors drive/sync.py manifest IO) ─────────
class SyncStatus(BaseModel):
    state: Literal["never_synced", "syncing", "ready", "error"]
    last_sync_at: datetime | None = None
    n_files: int = 0
    pending: int = 0
    last_error: str | None = None
    manifest_path: str | None = None


# ─── Conflicts (Option C — wired now via existing contradiction.py) ──────────
class ConflictFinding(BaseModel):
    entity_or_relation: str
    consistent: bool
    contradiction: str | None = None
    chunks: list[str]


class ConflictReport(BaseModel):
    findings: list[ConflictFinding]
    n_findings: int
    generated_at: datetime


# ─── Draft (Option D — Writer; wired now via proposal_pipeline.py) ───────────
class DraftRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    n_sections: int = Field(default=3, ge=1, le=8)
    locale: Literal["en", "id"] = "en"


class RubricMean(BaseModel):
    faithfulness: float
    citation_coverage: float
    contradiction_freeness: float
    section_coverage: float
    tone: float
    mean: float


class DraftResponse(BaseModel):
    topic: str
    locale: str
    markdown: str
    rubric: RubricMean | None = None
    generated_at: datetime


# ─── Action items (Option B — stub in step 2, wired in step 7) ───────────────
class ActionExtractRequest(BaseModel):
    doc_id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_of(self) -> ActionExtractRequest:
        if not (self.doc_id or self.text):
            raise ValueError("must provide either `doc_id` or `text`")
        return self


class ActionItem(BaseModel):
    assignee: str
    action: str
    due: str | None = None
    source_chunk: str | None = None


class ActionExtractResponse(BaseModel):
    items: list[ActionItem]
    n_items: int
    source: str  # "doc:..." or "text"


# ─── Drift (Option E — recent reads jsonl; scan is stubbed in step 2) ────────
class DriftEvent(BaseModel):
    type: Literal["doc_added", "doc_changed", "doc_removed", "scope_drift", "tone_drift"]
    doc_id: str
    timestamp: datetime
    summary: str


class DriftScanResponse(BaseModel):
    run_id: str
    status: Literal["queued"]
    accepted_at: datetime


class DriftRecentResponse(BaseModel):
    events: list[DriftEvent]
    n_events: int
    source_path: str
