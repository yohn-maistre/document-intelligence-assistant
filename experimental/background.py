"""Background Ingestion Agent — APScheduler + asyncio, ~80 LOC.

The "specialized async agent" 2026 pattern, sized for klerk. Watches a corpus
source dir (default `data/raw/`), detects added/changed/removed files via
mtime + sha256, and re-indexes only the deltas. Optionally re-extracts the
KG for affected docs.

Run:
    klerk bg start              # foreground, ctrl-C to stop
    klerk bg start --once       # one cycle then exit (CI / cron mode)
    klerk bg status             # last cycle, changes detected

No external memory framework (Cognee / Letta / mem0); see design-decisions.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _state_dir() -> Path:
    p = Path(os.environ.get("KLERK_BG_STATE_DIR", ".klerk"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path() -> Path:
    return _state_dir() / "bg_state.json"


def _watch_dir() -> Path:
    p = Path(os.environ.get("KLERK_BG_WATCH_DIR", "data/raw"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class CycleReport:
    cycle_ts: float
    watched_dir: str
    n_added: int
    n_changed: int
    n_removed: int
    n_indexed: int
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_ts": self.cycle_ts,
            "watched_dir": self.watched_dir,
            "n_added": self.n_added,
            "n_changed": self.n_changed,
            "n_removed": self.n_removed,
            "n_indexed": self.n_indexed,
            "errors": self.errors,
        }


def _load_state() -> dict[str, str]:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state: dict[str, str]) -> None:
    _state_path().write_text(json.dumps(state, indent=2))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _index_files(paths: list[Path]) -> tuple[int, list[str]]:
    """Parse + chunk + upsert the given file list. Returns (n_indexed, errors)."""
    if not paths:
        return 0, []
    from klerk.parse import parse
    from klerk.rag.chunker import chunk_text
    from klerk.rag.store import upsert_chunks

    n_total = 0
    errors: list[str] = []
    for f in paths:
        try:
            doc = parse(f)
            chunks = chunk_text(doc.text, doc_id=doc.doc_id, locale=doc.locale, source=str(doc.source))
            if chunks:
                n_total += upsert_chunks(chunks)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {type(e).__name__}: {e}")
    return n_total, errors


def run_cycle() -> CycleReport:
    """One ingestion cycle: detect deltas, re-index changed files."""
    watch = _watch_dir()
    state = _load_state()  # path → sha256
    seen: dict[str, str] = {}

    added: list[Path] = []
    changed: list[Path] = []
    files = [p for p in watch.rglob("*") if p.is_file() and not p.name.startswith(".")]

    for f in files:
        try:
            sha = _sha256(f)
        except Exception:  # noqa: BLE001
            continue
        rel = str(f.relative_to(watch))
        seen[rel] = sha
        if rel not in state:
            added.append(f)
        elif state[rel] != sha:
            changed.append(f)

    removed = sorted(set(state) - set(seen))

    n_indexed, errors = _index_files(added + changed)
    _save_state(seen)

    report = CycleReport(
        cycle_ts=time.time(),
        watched_dir=str(watch),
        n_added=len(added),
        n_changed=len(changed),
        n_removed=len(removed),
        n_indexed=n_indexed,
        errors=errors,
    )
    _state_dir().joinpath("bg_last_cycle.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str)
    )
    return report


def last_report() -> CycleReport | None:
    p = _state_dir() / "bg_last_cycle.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return CycleReport(**data)


def start(*, interval_seconds: int = 60, once: bool = False):
    """Start the scheduler. If `once`, run a single cycle and return.

    Foreground operation (the verb prints status); reviewer ^C to stop.
    """
    if once:
        return run_cycle()

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_cycle, "interval", seconds=interval_seconds, id="klerk_bg")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
