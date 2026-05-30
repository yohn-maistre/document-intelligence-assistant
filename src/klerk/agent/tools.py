"""The six orchestrator tools — LangChain wrappers over existing klerk fns.

Each tool wraps a Python function klerk already ships and the FastAPI surface
already exposes, so the orchestrator and the REST endpoints share one
implementation. Every call appends one line to `.klerk/activity-log.jsonl`
(ts, session_id, tool, status, duration_ms, summary) which the Studio
Activity panel (cluster 5) tails.

`display_name` on each tool ("klerk search hybrid") is what the Activity UI
shows; the LangChain tool `name` is the snake_case identifier the LLM emits.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path

from langchain_core.tools import tool

# Per-request session id, set by the orchestrator so tool logs are attributable
# without threading it through every tool signature.
_current_session: ContextVar[str | None] = ContextVar("klerk_session", default=None)

DISPLAY_NAMES = {
    "search_hybrid": "klerk search hybrid",
    "extract_actions": "klerk extract actions",
    "draft_doc": "klerk draft doc",
    "scan_conflicts": "klerk scan conflicts",
    "ingest_path": "klerk ingest path",
    "sync_drive": "klerk sync drive",
}


def set_session(session_id: str | None) -> None:
    _current_session.set(session_id)


def _activity_path() -> Path:
    p = Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "activity-log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _log_activity(tool_name: str, status: str, duration_ms: float, summary: str) -> None:
    rec = {
        "ts": time.time(),
        "session_id": _current_session.get(),
        "tool": tool_name,
        "display_name": DISPLAY_NAMES.get(tool_name, tool_name),
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "summary": summary,
    }
    try:
        with _activity_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass  # activity logging is best-effort, never breaks a tool call


def _timed(tool_name: str, fn: Callable[[], tuple[str, str]]) -> str:
    """Run `fn`, log timing/status, return the string result. fn returns
    (result_text, summary_for_activity)."""
    start = time.perf_counter()
    try:
        result, summary = fn()
        _log_activity(tool_name, "ok", (time.perf_counter() - start) * 1000, summary)
        return result
    except Exception as e:  # noqa: BLE001 - surface tool errors to the LLM as text
        msg = f"{type(e).__name__}: {e}"
        _log_activity(tool_name, "error", (time.perf_counter() - start) * 1000, msg)
        return f"TOOL ERROR ({tool_name}): {msg}"


# ─── Tools ───────────────────────────────────────────────────────────────────
@tool
def search_hybrid(query: str) -> str:
    """Retrieve grounding chunks from the corpus via hybrid (vector + BM25 +
    rerank) search. Returns chunks tagged [doc_id:chunk_idx] for citation."""

    def run() -> tuple[str, str]:
        from klerk.rag.retrieve import search_hybrid as _search

        hits = _search(query, k_initial=16, k_final=8, rerank=True)
        if not hits:
            return ("No matching chunks in the corpus.", "0 chunks")
        body = "\n\n".join(f"[{h.chunk_id}] {h.text}" for h in hits)
        return (body, f"{len(hits)} chunks")

    return _timed("search_hybrid", run)


@tool
def extract_actions(text: str = "", doc_id: str = "") -> str:
    """Extract structured action items (assignee, action, due, priority) from a
    text snippet or an indexed doc_id. Pass exactly one of text or doc_id."""

    def run() -> tuple[str, str]:
        from klerk.agent.action_items import extract

        result = extract(
            doc_id=doc_id or None,
            text=text or None,
        )
        return (result.model_dump_json(indent=2), f"{len(result.items)} action items")

    return _timed("extract_actions", run)


@tool
def draft_doc(topic: str, n_sections: int = 3, locale: str = "en") -> str:
    """Run the adversarial multi-drafter doc-writer to produce a multi-section
    document on `topic`. Use only when the user asks to write/draft a document."""

    def run() -> tuple[str, str]:
        from klerk.agent.writer import write_draft

        summary = write_draft(topic, n_sections=n_sections, locale=locale)
        rubric = f"rubric {summary.rubric_mean:.2f}" if summary.rubric_mean else "no rubric"
        body = "\n\n".join(f"## {s.title}\n{s.body}" for s in summary.sections)
        return (body, f"{len(summary.sections)} sections, {rubric}")

    return _timed("draft_doc", run)


@tool
def scan_conflicts(locale: str = "en") -> str:
    """Sweep the knowledge graph for cross-document contradictions. Use when
    the user asks about conflicts, inconsistencies, or which source is right."""

    def run() -> tuple[str, str]:
        from klerk.orchestrate import conflict_graph

        state = conflict_graph.run(locale=locale)
        n = state.get("n_findings", 0)
        return (state.get("report_markdown", "(no report)"), f"{n} conflicts")

    return _timed("scan_conflicts", run)


@tool
def ingest_path(path: str) -> str:
    """Ingest a local directory of documents into the corpus (parse → chunk →
    embed → index). Use only when the user explicitly asks to load files."""

    def run() -> tuple[str, str]:
        import uuid

        from klerk.api.ingest_runner import read_status, run_ingest

        run_id = f"ing_{uuid.uuid4().hex[:8]}"
        run_ingest(run_id, source="path", path=path)
        status = read_status(run_id)
        if status is None:
            return ("ingest produced no status", "no status")
        return (status.model_dump_json(indent=2), f"{status.n_files} files, {status.state}")

    return _timed("ingest_path", run)


@tool
def sync_drive() -> str:
    """Pull new/changed/removed files from the configured Drive folder into the
    corpus. Use only when the user explicitly asks to sync Drive."""

    def run() -> tuple[str, str]:
        from klerk.drive.sync import sync

        report = sync()
        d = report.diff
        return (
            f"added={len(d.added)} changed={len(d.changed)} removed={len(d.removed)} "
            f"downloaded={len(report.downloaded)}",
            f"+{len(d.added)} ~{len(d.changed)} -{len(d.removed)}",
        )

    return _timed("sync_drive", run)


ALL_TOOLS = [
    search_hybrid,
    extract_actions,
    draft_doc,
    scan_conflicts,
    ingest_path,
    sync_drive,
]
