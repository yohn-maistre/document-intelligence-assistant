"""SQLite checkpoint store — the Dynamic-Workflows resumability extract.

Long-running ops (proposal pipeline, FAQ build, KG extraction) persist their
intermediate progress here. A killed run resumes by reading the latest
checkpoint for its `run_id` and skipping completed stages.

Schema (per run):
    runs (run_id PK, op, topic, locale, started_at, completed_at)
    steps (run_id FK, step_idx, name, status, payload_json, ts)

`payload_json` carries whatever the producing step wants to hand to the
resuming step (e.g. the section scope, the drafts so far, etc.).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    op TEXT NOT NULL,
    topic TEXT,
    locale TEXT,
    started_at REAL NOT NULL,
    completed_at REAL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL,
    step_idx INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT,
    ts REAL NOT NULL,
    PRIMARY KEY (run_id, step_idx)
);
CREATE INDEX IF NOT EXISTS idx_runs_op ON runs (op);
CREATE INDEX IF NOT EXISTS idx_steps_status ON steps (run_id, status);
"""


def _db_path() -> Path:
    p = Path(os.environ.get("KLERK_CHECKPOINT_DB", ".klerk/checkpoints.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(_db_path()))
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


@dataclass
class StepRecord:
    step_idx: int
    name: str
    status: str  # "started" | "done" | "failed"
    payload: dict[str, Any]
    ts: float


# ─── Run lifecycle ──────────────────────────────────────────────────────────
def new_run(op: str, *, topic: str | None = None, locale: str | None = None) -> str:
    run_id = f"{op}-{uuid.uuid4().hex[:10]}"
    with _conn() as c:
        c.execute(
            "INSERT INTO runs (run_id, op, topic, locale, started_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, op, topic, locale, time.time()),
        )
    return run_id


def complete_run(run_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE runs SET completed_at = ? WHERE run_id = ?", (time.time(), run_id))


# ─── Step lifecycle ─────────────────────────────────────────────────────────
def record_step(run_id: str, step_idx: int, name: str, status: str, payload: dict | None = None) -> None:
    payload_json = json.dumps(payload or {}, default=str, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO steps (run_id, step_idx, name, status, payload_json, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, step_idx, name, status, payload_json, time.time()),
        )


def steps_for(run_id: str) -> list[StepRecord]:
    with _conn() as c:
        rows = c.execute(
            "SELECT step_idx, name, status, payload_json, ts FROM steps "
            "WHERE run_id = ? ORDER BY step_idx",
            (run_id,),
        ).fetchall()
    return [
        StepRecord(step_idx=r[0], name=r[1], status=r[2], payload=json.loads(r[3] or "{}"), ts=r[4])
        for r in rows
    ]


def last_done_step(run_id: str) -> int:
    """Returns the highest step_idx with status='done', or -1 if none."""
    with _conn() as c:
        row = c.execute(
            "SELECT MAX(step_idx) FROM steps WHERE run_id = ? AND status = 'done'",
            (run_id,),
        ).fetchone()
    return row[0] if row and row[0] is not None else -1


# ─── Inspection ─────────────────────────────────────────────────────────────
def list_runs(op: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as c:
        if op:
            rows = c.execute(
                "SELECT run_id, op, topic, locale, started_at, completed_at FROM runs "
                "WHERE op = ? ORDER BY started_at DESC LIMIT ?",
                (op, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT run_id, op, topic, locale, started_at, completed_at FROM runs "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [
        {
            "run_id": r[0],
            "op": r[1],
            "topic": r[2],
            "locale": r[3],
            "started_at": r[4],
            "completed_at": r[5],
        }
        for r in rows
    ]
