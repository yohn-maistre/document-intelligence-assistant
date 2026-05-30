"""Background ingestion runner — drives /ingest from FastAPI BackgroundTasks.

Two sources, one unified status surface:
  - source=path: walk a local directory, parse → chunk → embed → upsert
  - source=drive: scaffolded; the full Drive API path lands in step 3 and
    will call into klerk.drive.sync. For step 2 it raises a clean error so
    the endpoint contract is honest about what's wired.

Status is persisted as one JSON file per run under .klerk/ingest-runs/{run_id}.json
so /sync-status and (future) admin tooling can read it without IPC.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from klerk.api.models import IngestRunStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def runs_dir() -> Path:
    """Resolved at call time so KLERK_STATE_DIR env overrides take effect per-test."""
    p = Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "ingest-runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def status_path(run_id: str) -> Path:
    return runs_dir() / f"{run_id}.json"


def write_status(status: IngestRunStatus) -> None:
    status_path(status.run_id).write_text(status.model_dump_json(indent=2))


def read_status(run_id: str) -> IngestRunStatus | None:
    p = status_path(run_id)
    if not p.exists():
        return None
    return IngestRunStatus.model_validate_json(p.read_text())


def list_runs(limit: int = 20) -> list[IngestRunStatus]:
    d = runs_dir()
    if not d.exists():
        return []
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[IngestRunStatus] = []
    for f in files[:limit]:
        try:
            out.append(IngestRunStatus.model_validate_json(f.read_text()))
        except Exception:  # noqa: BLE001
            continue
    return out


def run_ingest(
    run_id: str,
    *,
    source: Literal["drive", "path"],
    path: str | None = None,
    folder_id: str | None = None,
) -> None:
    """The function FastAPI BackgroundTasks invokes. Updates status as it goes."""
    status = IngestRunStatus(
        run_id=run_id,
        source=source,
        state="running",
        started_at=_now(),
    )
    write_status(status)

    try:
        if source == "path":
            if not path:
                raise ValueError("source='path' requires a `path`")
            n_files, n_chunks = _ingest_local_path(path)
        elif source == "drive":
            n_files, n_chunks = _ingest_drive(folder_id=folder_id)
        else:  # pragma: no cover - Pydantic enum guards this
            raise ValueError(f"unknown source: {source}")

        status = status.model_copy(update={
            "state": "complete",
            "completed_at": _now(),
            "n_files": n_files,
            "n_chunks": n_chunks,
        })
    except Exception as e:  # noqa: BLE001 - we want the message in the run file
        status = status.model_copy(update={
            "state": "failed",
            "completed_at": _now(),
            "error": f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
        })

    write_status(status)


def _ingest_local_path(path: str) -> tuple[int, int]:
    """Walk the path, parse, chunk, embed, upsert. Returns (n_files, n_chunks)."""
    from klerk.parse import parse
    from klerk.rag.chunker import chunk_text
    from klerk.rag.store import upsert_chunks

    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"ingest path not found: {path}")

    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p.name != "README.md"]
    n_chunks = 0
    n_files = 0
    for f in files:
        try:
            doc = parse(f)
        except Exception:  # noqa: BLE001 - skip unparseable; surface in completion log later
            continue
        chunks = chunk_text(
            doc.text,
            doc_id=doc.doc_id,
            locale=doc.locale,
            source=str(doc.source),
        )
        if chunks:
            n_chunks += upsert_chunks(chunks)
            n_files += 1
    return n_files, n_chunks


def _ingest_drive(*, folder_id: str | None = None) -> tuple[int, int]:
    """Drive ingest: sync the folder to a local dir, then walk + index it."""
    from klerk.drive.sync import download_dir, sync as drive_sync

    report = drive_sync(folder_id=folder_id)
    return _ingest_local_path(report.download_dir)
