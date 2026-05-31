"""FastAPI server — the primary HTTP surface for klerk.

Endpoints (see HANDOFF.md section 7 step 2):
  GET  /health                  readiness + per-subsystem status
  POST /chat                    SSE stream over Nemotron-grounded answers
  POST /ingest                  kick off corpus ingestion (BackgroundTasks)
  GET  /ingest/runs             list recent ingest runs
  GET  /sync-status             last Drive sync state + counts
  POST /actions/extract         action-item extraction       (step 7: full agent)
  POST /conflicts/scan          cross-doc contradiction sweep
  POST /draft                   multi-drafter adversarial doc-writer
  GET  /drift/recent            last N drift events from .klerk/drift-events.jsonl
  POST /drift/scan              trigger a fresh drift scan   (step 7: full agent)

Run locally:
  uvicorn klerk.api.server:app --reload
or:
  klerk-api  (added in pyproject.toml [project.scripts])
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.base import BaseHTTPMiddleware

from klerk import __version__
from klerk.api.ingest_runner import (
    list_runs as list_ingest_runs,
    read_status as read_ingest_status,
    run_ingest,
    write_status as write_ingest_status,
)
from klerk.api.models import (
    ActionExtractRequest,
    ActionExtractResponse,
    ChatRequest,
    ConflictFinding,
    ConflictReport,
    DraftRequest,
    DraftResponse,
    DriftEvent,
    DriftRecentResponse,
    DriftScanResponse,
    HealthChecks,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    IngestRunStatus,
    RubricMean,
    SyncStatus,
)
from klerk.llm.nemotron import NemotronConfig


def _state_dir() -> Path:
    """Resolved at call time so per-test KLERK_STATE_DIR overrides apply."""
    return Path(os.environ.get("KLERK_STATE_DIR", ".klerk"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Middleware: TTFT + total-latency headers on every response ──────────────
class LatencyMiddleware(BaseHTTPMiddleware):
    """Stamp X-Klerk-TTFT-MS + X-Klerk-Total-MS on every response.

    Non-streaming responses: TTFT == total (single measurement).
    SSE responses: the handler sets X-Klerk-TTFT-MS itself; this middleware
    only fills in total. (For SSE the "TTFT" header is informational; the
    'done' event in the stream carries the canonical timing.)
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        total_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Klerk-Total-MS"] = f"{total_ms:.1f}"
        if "X-Klerk-TTFT-MS" not in response.headers:
            response.headers["X-Klerk-TTFT-MS"] = f"{total_ms:.1f}"
        return response


# ─── Lifespan: minimal — models lazy-load on first hit ───────────────────────
@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _state_dir().mkdir(parents=True, exist_ok=True)
    yield


# ─── App factory ─────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="klerk — Document Intelligence Assistant",
        description=(
            "Production HTTP surface. Streaming chat, incremental Drive ingest, "
            "five agentic capabilities (Escalation / Action Items / Conflict Reporter / "
            "Writer / Drift). Backed by Nemotron via a Cloudflare-tunneled LiteLLM proxy."
        ),
        version=__version__,
        lifespan=_lifespan,
    )
    app.add_middleware(LatencyMiddleware)

    @app.exception_handler(RuntimeError)
    async def _runtime_error(_: Request, exc: RuntimeError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    _wire_health(app)
    _wire_chat(app)
    _wire_ingest(app)
    _wire_sync(app)
    _wire_conflicts(app)
    _wire_draft(app)
    _wire_actions(app)
    _wire_drift(app)
    return app


# ═══════════════════════════════════════════════════════════════════════════
# /health
# ═══════════════════════════════════════════════════════════════════════════
def _readiness_checks() -> HealthChecks:
    """Quick per-subsystem snapshot. No outbound network calls."""
    has_llm_creds = bool(
        os.environ.get("LITELLM_KEY") and os.environ.get("CF_CLIENT_ID")
    )
    drive_configured = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    try:
        from klerk.rag.store import CORPUS_TABLE, open_db

        db = open_db()
        lance_state = "ready" if CORPUS_TABLE in db.list_tables() else "empty"
    except Exception:  # noqa: BLE001
        lance_state = "error"

    return HealthChecks(
        nemotron_proxy="ready" if has_llm_creds else "unconfigured",
        lancedb=lance_state,
        bge_m3="lazy",
        drive="configured" if drive_configured else "unconfigured",
    )


def _wire_health(app: FastAPI) -> None:
    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health() -> HealthResponse:
        checks = _readiness_checks()
        is_ok = checks.nemotron_proxy == "ready" and checks.lancedb != "error"
        return HealthResponse(
            status="ok" if is_ok else "degraded",
            version=__version__,
            checks=checks,
        )


# ═══════════════════════════════════════════════════════════════════════════
# /chat — SSE
# ═══════════════════════════════════════════════════════════════════════════
async def _chat_event_stream(
    req: ChatRequest,
    start: float,
) -> AsyncIterator[dict]:
    """Drive one chat turn through the LangGraph orchestrator.

    The orchestrator (klerk.agent.orchestrator) routes among six tools, yields
    session / tool_call / tool_result / token / citations / done events, and
    pre-seeds search_hybrid every turn. This handler layers on multi-turn
    memory (SessionStore) and the low-confidence escalation hook, then persists
    the exchange.
    """
    import uuid

    from klerk.agent import orchestrator
    from klerk.api.session import get_store

    store = get_store()
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:12]}"

    history: list[dict[str, str]] | None = None
    if req.history_mode == "auto" and store.exists(session_id):
        try:
            history = store.build_prompt_history(session_id)
        except Exception:  # noqa: BLE001 - history is best-effort
            history = None

    answer = ""
    confidence = 1.0
    n_chunks = 0
    async for event in orchestrator.arun(
        req.query, session_id=session_id, locale=req.locale, history=history
    ):
        # Tap the stream to accumulate answer text + confidence for persistence
        # and the escalation decision, then re-yield unchanged.
        etype = event.get("event")
        if etype == "token":
            answer += json.loads(event["data"]).get("text", "")
        elif etype == "citations":
            confidence = json.loads(event["data"]).get("confidence", confidence)
        elif etype == "done":
            n_chunks = json.loads(event["data"]).get("n_chunks", 0)
        yield event

    # Low-confidence escalation hook: draft an email to a human owner. Failures
    # are silent so the chat stream is never broken by escalation logic.
    escalation_threshold = float(os.environ.get("KLERK_ESCALATION_THRESHOLD", "0.3"))
    if confidence < escalation_threshold and n_chunks:
        try:
            from klerk.agent.escalation import draft as escalation_draft

            draft = await asyncio.to_thread(
                escalation_draft,
                question=req.query,
                confidence=confidence,
                retrieved_excerpt=answer[:1200],
                locale=req.locale,
            )
            yield {"event": "escalation", "data": draft.model_dump_json()}
        except Exception:  # noqa: BLE001
            pass

    # Persist the turn (best-effort).
    try:
        store.append(session_id, "user", req.query)
        if answer:
            store.append(session_id, "assistant", answer)
    except Exception:  # noqa: BLE001
        pass


def _wire_chat(app: FastAPI) -> None:
    @app.post("/chat", tags=["chat"])
    async def chat(req: ChatRequest):
        cfg = NemotronConfig.from_env()
        if not cfg.api_key:
            raise HTTPException(
                status_code=503,
                detail="Nemotron proxy not configured (LITELLM_KEY missing).",
            )
        start = time.perf_counter()
        return EventSourceResponse(
            _chat_event_stream(req, start),
            headers={"X-Klerk-TTFT-MS": "streaming"},
        )


# ═══════════════════════════════════════════════════════════════════════════
# /ingest + /ingest/runs
# ═══════════════════════════════════════════════════════════════════════════
def _wire_ingest(app: FastAPI) -> None:
    @app.post(
        "/ingest",
        response_model=IngestResponse,
        status_code=202,
        tags=["ingest"],
    )
    async def ingest(req: IngestRequest, bg: BackgroundTasks) -> IngestResponse:
        run_id = f"ing_{uuid.uuid4().hex[:12]}"
        # Seed the status file so /ingest/runs/{run_id} returns immediately.
        write_ingest_status(IngestRunStatus(
            run_id=run_id,
            source=req.source,
            state="queued",
        ))
        bg.add_task(
            run_ingest,
            run_id,
            source=req.source,
            path=req.path,
            folder_id=req.folder_id,
        )
        return IngestResponse(run_id=run_id, status="queued", accepted_at=_now())

    @app.get(
        "/ingest/runs",
        response_model=list[IngestRunStatus],
        tags=["ingest"],
    )
    async def list_runs(limit: int = Query(default=20, ge=1, le=200)):
        return list_ingest_runs(limit=limit)

    @app.get(
        "/ingest/runs/{run_id}",
        response_model=IngestRunStatus,
        tags=["ingest"],
    )
    async def get_run(run_id: str):
        status = read_ingest_status(run_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"no such run: {run_id}")
        return status


# ═══════════════════════════════════════════════════════════════════════════
# /sync-status — Drive manifest snapshot
# ═══════════════════════════════════════════════════════════════════════════
def _wire_sync(app: FastAPI) -> None:
    @app.get("/sync-status", response_model=SyncStatus, tags=["ingest"])
    async def sync_status() -> SyncStatus:
        from klerk.drive.sync import load_manifest, manifest_path

        path = manifest_path()
        if not path.exists():
            return SyncStatus(state="never_synced", manifest_path=str(path))

        manifest = load_manifest()
        try:
            last_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            last_modified = None

        return SyncStatus(
            state="ready" if manifest else "never_synced",
            last_sync_at=last_modified,
            n_files=len(manifest),
            pending=0,
            manifest_path=str(path),
        )


# ═══════════════════════════════════════════════════════════════════════════
# /conflicts/scan — wired via existing contradiction.scan()
# ═══════════════════════════════════════════════════════════════════════════
def _wire_conflicts(app: FastAPI) -> None:
    @app.post("/conflicts/scan", response_model=ConflictReport, tags=["agents"])
    async def conflicts_scan(locale: str = Query(default="en", pattern="^(en|id)$")):
        # Step 8: route through the LangGraph spine instead of calling
        # contradiction.scan directly. The 4-node graph (retrieve_docs →
        # pair_facts → judge_conflict → format_report) gives us
        # per-node tracing and a clean place to add checkpointing.
        from klerk.orchestrate.conflict_graph import run as run_graph

        state = await asyncio.to_thread(run_graph, locale)
        findings = [
            ConflictFinding(
                entity_or_relation=f["entity_or_relation"],
                consistent=f["consistent"],
                contradiction=f.get("contradiction") or None,
                chunks=f["evidence_chunks"],
            )
            for f in state.get("findings", [])
        ]
        return ConflictReport(
            findings=findings,
            n_findings=state.get("n_findings", len(findings)),
            generated_at=_now(),
        )


# ═══════════════════════════════════════════════════════════════════════════
# /draft — multi-drafter adversarial doc-writer
# ═══════════════════════════════════════════════════════════════════════════
def _wire_draft(app: FastAPI) -> None:
    @app.post("/draft", response_model=DraftResponse, tags=["agents"])
    async def draft(req: DraftRequest):
        # Route through the writer façade (step 7) so the internal Proposal
        # type doesn't leak into the API layer. The full per-section trace
        # (drafter-A / drafter-B / adjudication) is still reachable via the
        # internal doc_writer.propose() if needed.
        from klerk.agent.doc_writer import propose

        proposal = await asyncio.to_thread(
            propose,
            req.topic,
            n_sections=req.n_sections,
            locale=req.locale,
        )
        rubric_payload: RubricMean | None = None
        if proposal.summary_rubric:
            r = proposal.summary_rubric
            rubric_payload = RubricMean(
                faithfulness=r.faithfulness,
                citation_coverage=r.citation_coverage,
                contradiction_freeness=r.contradiction_freeness,
                section_coverage=r.section_coverage,
                tone=r.tone,
                mean=r.mean,
            )
        return DraftResponse(
            topic=req.topic,
            locale=req.locale,
            markdown=proposal.to_markdown(),
            rubric=rubric_payload,
            generated_at=_now(),
        )


# ═══════════════════════════════════════════════════════════════════════════
# /actions/extract — capability B (action_items.extract)
# ═══════════════════════════════════════════════════════════════════════════
def _wire_actions(app: FastAPI) -> None:
    @app.post(
        "/actions/extract",
        response_model=ActionExtractResponse,
        tags=["agents"],
    )
    async def actions_extract(req: ActionExtractRequest, locale: str = Query(default="en", pattern="^(en|id)$")):
        from klerk.agent.action_items import extract
        from klerk.api.models import ActionItem as ActionItemPublic

        result = await asyncio.to_thread(
            extract, doc_id=req.doc_id, text=req.text, locale=locale,
        )
        return ActionExtractResponse(
            items=[
                ActionItemPublic(
                    assignee=item.assignee,
                    action=item.action,
                    due=item.due,
                    source_chunk=item.source_chunk,
                )
                for item in result.items
            ],
            n_items=len(result.items),
            source=result.source,
        )


# ═══════════════════════════════════════════════════════════════════════════
# /drift/recent + /drift/scan
# ═══════════════════════════════════════════════════════════════════════════
def _drift_events_path() -> Path:
    return _state_dir() / "drift-events.jsonl"


def _wire_drift(app: FastAPI) -> None:
    @app.get("/drift/recent", response_model=DriftRecentResponse, tags=["agents"])
    async def drift_recent(limit: int = Query(default=20, ge=1, le=500)):
        path = _drift_events_path()
        if not path.exists():
            return DriftRecentResponse(events=[], n_events=0, source_path=str(path))
        events: list[DriftEvent] = []
        try:
            for line in path.read_text().splitlines()[-limit:]:
                if not line.strip():
                    continue
                events.append(DriftEvent.model_validate_json(line))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"drift-events.jsonl unreadable: {type(e).__name__}: {e}",
            )
        return DriftRecentResponse(
            events=events,
            n_events=len(events),
            source_path=str(path),
        )

    @app.post(
        "/drift/scan",
        response_model=DriftScanResponse,
        status_code=202,
        tags=["agents"],
    )
    async def drift_scan(bg: BackgroundTasks):
        from klerk.agent.drift import scan as run_drift_scan

        run_id = f"drf_{uuid.uuid4().hex[:10]}"
        # Fire-and-forget the actual scan; results land in
        # .klerk/drift-events.jsonl which /drift/recent reads.
        def _run_and_log():
            report = run_drift_scan()
            # Best-effort: stamp the report's own run_id into a status file
            try:
                status_path = _state_dir() / "drift-runs" / f"{run_id}.json"
                status_path.parent.mkdir(parents=True, exist_ok=True)
                status_path.write_text(report.model_dump_json(indent=2))
            except OSError:
                pass

        bg.add_task(_run_and_log)
        return DriftScanResponse(run_id=run_id, status="queued", accepted_at=_now())


# ─── Module-level app for `uvicorn klerk.api.server:app` ─────────────────────
app = create_app()


def main() -> None:
    """Entry point exposed via [project.scripts] klerk-api = ..."""
    import uvicorn

    host = os.environ.get("KLERK_API_HOST", "0.0.0.0")
    port = int(os.environ.get("KLERK_API_PORT", "8000"))
    uvicorn.run(
        "klerk.api.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
