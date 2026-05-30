"""Capability E — Drift agent.

Compares the live LanceDB corpus snapshot against a persisted "previous"
snapshot at `.klerk/drift-snapshot.json` and emits structured DriftEvent
records to `.klerk/drift-events.jsonl`. The API endpoint
`GET /drift/recent` reads that jsonl; `POST /drift/scan` triggers a fresh
run (the scheduled APScheduler hook does the same at 02:00 UTC).

Event types:
  - doc_added     : doc_id appeared in the corpus, no prior snapshot
  - doc_changed   : doc_id present in both, chunk-hash digest changed
  - doc_removed   : doc_id dropped from the corpus
  - scope_drift   : (heuristic) chunk centroid moved by > threshold cosine
                    distance — a doc started talking about something else.
                    Only emitted when an embed model is loaded; skipped in
                    mock-backend / CI runs.

The agent is intentionally cheap: snapshot is `{doc_id: sha256(sorted_chunks)}`,
diff is a dict comparison, no LLM calls. scope_drift is the only
embedding-dependent signal and runs only when chunks have a `vector` column.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from klerk.agent._models import DriftEvent, DriftScanReport

SCOPE_DRIFT_THRESHOLD = float(os.environ.get("KLERK_DRIFT_THRESHOLD", "0.25"))


def _state_dir() -> Path:
    p = Path(os.environ.get("KLERK_STATE_DIR", ".klerk"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def snapshot_path() -> Path:
    return _state_dir() / "drift-snapshot.json"


def events_path() -> Path:
    return _state_dir() / "drift-events.jsonl"


# ─── Snapshot helpers ────────────────────────────────────────────────────────
def _hash_doc(chunks: list[dict]) -> tuple[str, list[float] | None]:
    """sha256 over chunk texts + the dense centroid if vectors are present."""
    sorted_chunks = sorted(chunks, key=lambda r: r.get("chunk_id", ""))
    digest = hashlib.sha256()
    for c in sorted_chunks:
        digest.update(c.get("text", "").encode("utf-8"))
    vectors = [c.get("vector") for c in sorted_chunks if c.get("vector") is not None]
    centroid: list[float] | None = None
    if vectors:
        arr = np.array(vectors, dtype=np.float32)
        centroid = arr.mean(axis=0).tolist()
    return digest.hexdigest(), centroid


def _load_snapshot() -> dict[str, dict]:
    p = snapshot_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_snapshot(snap: dict[str, dict]) -> None:
    p = snapshot_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(snap, indent=2))
    tmp.replace(p)


def _build_snapshot() -> tuple[dict[str, dict], int]:
    """Pull every doc from LanceDB, hash + centroid each. Returns (snapshot, n_docs)."""
    from klerk.rag.store import CORPUS_TABLE, open_db

    db = open_db()
    if CORPUS_TABLE not in db.list_tables():
        return {}, 0
    df = db.open_table(CORPUS_TABLE).to_pandas()
    if df.empty:
        return {}, 0

    snap: dict[str, dict] = {}
    for doc_id in sorted(df["doc_id"].unique()):
        rows = df[df["doc_id"] == doc_id].to_dict("records")
        digest, centroid = _hash_doc(rows)
        snap[doc_id] = {
            "digest": digest,
            "centroid": centroid,
            "n_chunks": len(rows),
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }
    return snap, len(snap)


# ─── Drift detection ─────────────────────────────────────────────────────────
def _cosine(a: list[float] | None, b: list[float] | None) -> float | None:
    if a is None or b is None:
        return None
    av = np.array(a, dtype=np.float32)
    bv = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom == 0:
        return None
    return float(np.dot(av, bv) / denom)


def _classify_change(doc_id: str, prev: dict, curr: dict) -> list[DriftEvent]:
    """Emit one or more events for a doc that exists in both snapshots."""
    events: list[DriftEvent] = []
    if prev.get("digest") == curr.get("digest"):
        return events  # unchanged

    now = datetime.now(timezone.utc)
    events.append(
        DriftEvent(
            type="doc_changed",
            doc_id=doc_id,
            timestamp=now,
            summary=(
                f"Content digest changed (chunks {prev.get('n_chunks')} → "
                f"{curr.get('n_chunks')})."
            ),
        )
    )

    # Scope drift only if both snapshots carry centroids and the cosine
    # distance crosses the threshold.
    sim = _cosine(prev.get("centroid"), curr.get("centroid"))
    if sim is not None and (1.0 - sim) >= SCOPE_DRIFT_THRESHOLD:
        events.append(
            DriftEvent(
                type="scope_drift",
                doc_id=doc_id,
                timestamp=now,
                summary=(
                    f"Semantic centroid moved by {1.0 - sim:.2f} cosine distance "
                    f"(threshold {SCOPE_DRIFT_THRESHOLD:.2f}) — doc may be talking "
                    "about a different topic now."
                ),
            )
        )
    return events


def _diff_snapshots(prev: dict[str, dict], curr: dict[str, dict]) -> list[DriftEvent]:
    events: list[DriftEvent] = []
    prev_ids = set(prev)
    curr_ids = set(curr)
    now = datetime.now(timezone.utc)

    for doc_id in sorted(curr_ids - prev_ids):
        events.append(
            DriftEvent(
                type="doc_added",
                doc_id=doc_id,
                timestamp=now,
                summary=f"New doc with {curr[doc_id].get('n_chunks', 0)} chunk(s).",
            )
        )
    for doc_id in sorted(prev_ids - curr_ids):
        events.append(
            DriftEvent(
                type="doc_removed",
                doc_id=doc_id,
                timestamp=now,
                summary="Doc dropped from the corpus.",
            )
        )
    for doc_id in sorted(prev_ids & curr_ids):
        events.extend(_classify_change(doc_id, prev[doc_id], curr[doc_id]))
    return events


def _append_events(events: list[DriftEvent]) -> None:
    if not events:
        return
    p = events_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for ev in events:
            f.write(ev.model_dump_json() + "\n")


# ─── Public scan ─────────────────────────────────────────────────────────────
def scan() -> DriftScanReport:
    """Compare current corpus against the persisted snapshot; emit events;
    persist the new snapshot. Returns a structured report."""
    run_id = f"drf_{uuid.uuid4().hex[:10]}"
    started = datetime.now(timezone.utc)
    try:
        prev = _load_snapshot()
        curr, n_docs = _build_snapshot()
        events = _diff_snapshots(prev, curr)
        _append_events(events)
        _save_snapshot(curr)
        return DriftScanReport(
            run_id=run_id,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            n_docs_scanned=n_docs,
            events=events,
        )
    except Exception as e:  # noqa: BLE001 - one bad scan shouldn't kill the scheduled job
        return DriftScanReport(
            run_id=run_id,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            n_docs_scanned=0,
            events=[],
            error=f"{type(e).__name__}: {e}",
        )
