"""Hermes memory trio — SOUL.md + MEMORY.md + a LanceDB recall table.

klerk's long-term memory follows the Hermes convention:

  - **SOUL.md**  — a stable identity sketch (who klerk is, how it behaves).
    Seeded once on first run, read verbatim and prefixed onto every chat turn.
  - **MEMORY.md** — an append-only, human-readable fact log. Every saved fact
    is timestamped and appended; nothing is ever deleted.
  - **`memory_v1`** — a LanceDB table mirroring the fact log as embeddings so
    facts can be recalled by semantic + lexical similarity (hybrid RRF).

All three live under `${KLERK_MEMORY_DIR}` or, by default,
`${XDG_DATA_HOME:-~/.local/share}/klerk/memory/`. Tests pass an explicit
`base_dir` (a tmp dir) so nothing touches the real home directory.

Embedding reuses `klerk.rag.embed`, so the `mock` backend
(`KLERK_EMBED_BACKEND=mock`) lets the save→recall roundtrip run in CI without
downloading model weights. Fusion reuses `klerk.rag.fusion.rrf_by_key` so the
recall ranking matches the corpus retriever's RRF behaviour.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from pydantic import BaseModel, Field

from klerk.rag.embed import EMBED_DIM, embed_passages, embed_query
from klerk.rag.fusion import rrf_by_key

MEMORY_TABLE = "memory_v1"
SOUL_FILE = "SOUL.md"
MEMORY_FILE = "MEMORY.md"

# Seed identity for SOUL.md — written once, on first run.
SEED_SOUL = """\
# klerk — SOUL

I am **klerk**, a document-intelligence agent for an Indonesian-Japanese SaaS
firm. I help operators reason over their internal corpus: contracts, meeting
minutes, policies, and product docs.

## Identity
- I work in **hybrid English / Bahasa Indonesia** workflows. I answer in the
  language I am addressed in, and I never assume monolingual context.
- I am precise and grounded. Every claim I make about the corpus is backed by
  a citation to a chunk_id.
- When the corpus does not support an answer, I say **"I don't know"** (or
  *"Saya tidak tahu"*) rather than guessing. I would rather escalate to a
  human than fabricate.

## Behaviour
- I cite sources inline as `[doc_id:chunk_idx]`.
- I prefer short, structured answers over long prose.
- I remember durable facts about the operator and their corpus across
  sessions, but I treat MEMORY as supporting context — never as a substitute
  for retrieving the primary source.
"""


class MemoryFact(BaseModel):
    """A single durable fact worth remembering across sessions."""

    fact: str = Field(..., description="The fact, phrased as a standalone statement.")
    kind: str = Field(
        default="note",
        description="Category, e.g. 'preference', 'entity', 'decision', 'note'.",
    )


@dataclass
class RecalledFact:
    """A fact returned by `recall`, with its fused relevance score."""

    fact: str
    kind: str
    ts: str
    score: float


def _default_base_dir() -> Path:
    """Resolve the memory base dir from env, else XDG, else ~/.local/share."""
    override = os.environ.get("KLERK_MEMORY_DIR", "").strip()
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / "klerk" / "memory"


def _memory_schema() -> pa.Schema:
    """Frozen schema so reloads across runs are stable."""
    return pa.schema(
        [
            pa.field("fact_id", pa.string(), nullable=False),
            pa.field("text", pa.string(), nullable=False),
            pa.field("kind", pa.string(), nullable=False),
            pa.field("ts", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), EMBED_DIM), nullable=False),
        ]
    )


class MemoryStore:
    """SOUL.md + MEMORY.md + the `memory_v1` LanceDB recall table.

    Pass an explicit `base_dir` (tests do this with a tmp dir). When omitted,
    falls back to `KLERK_MEMORY_DIR` / XDG / ~/.local/share.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else _default_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.soul_path = self.base_dir / SOUL_FILE
        self.memory_path = self.base_dir / MEMORY_FILE
        self._db_dir = self.base_dir / "lancedb"

    # ─── SOUL ────────────────────────────────────────────────────────────────
    def read_soul(self) -> str:
        """Return SOUL.md verbatim, seeding it from the klerk persona on first run."""
        if not self.soul_path.exists():
            self.soul_path.write_text(SEED_SOUL, encoding="utf-8")
        return self.soul_path.read_text(encoding="utf-8")

    def write_soul(self, content: str) -> None:
        """Overwrite SOUL.md (used by `klerk memory edit-soul`)."""
        self.soul_path.write_text(content, encoding="utf-8")

    # ─── DB ──────────────────────────────────────────────────────────────────
    def _open_db(self):
        self._db_dir.mkdir(parents=True, exist_ok=True)
        return lancedb.connect(str(self._db_dir))

    def _open_table_or_none(self):
        """Open `memory_v1`, or None if it doesn't exist.

        Opens directly rather than gating on `list_tables()`, whose result can
        lag a just-created table in the same process (LanceDB connection cache).
        """
        db = self._open_db()
        try:
            return db.open_table(MEMORY_TABLE)
        except (FileNotFoundError, ValueError):
            return None

    def _ensure_fts_index(self, table) -> None:
        """Create / refresh the BM25 FTS index on the text column (idempotent)."""
        # Benign on tiny / empty tables where LanceDB sometimes refuses.
        with contextlib.suppress(Exception):
            table.create_fts_index("text", replace=True)

    # ─── SAVE ────────────────────────────────────────────────────────────────
    def save(self, fact: str | MemoryFact) -> MemoryFact:
        """Append a fact to MEMORY.md, embed it, and insert into `memory_v1`.

        Returns the normalized `MemoryFact`. Works with the mock embed backend.
        """
        mf = MemoryFact(fact=fact) if isinstance(fact, str) else fact
        ts = datetime.now(UTC).isoformat(timespec="seconds")
        fact_id = f"{ts}:{abs(hash(mf.fact)) % 10_000_000:07d}"

        # 1. Append to the human-readable log.
        self._append_log(mf, ts)

        # 2. Embed + insert into LanceDB.
        vector = embed_passages([mf.fact])[0]
        row = {
            "fact_id": fact_id,
            "text": mf.fact,
            "kind": mf.kind,
            "ts": ts,
            "vector": vector.tolist(),
        }
        table = self._open_table_or_none()
        if table is not None:
            table.add([row])
        else:
            db = self._open_db()
            try:
                table = db.create_table(MEMORY_TABLE, data=[row], schema=_memory_schema())
            except (ValueError, OSError):
                # Race: table appeared between the open-check and create.
                table = db.open_table(MEMORY_TABLE)
                table.add([row])
        self._ensure_fts_index(table)
        return mf

    def _append_log(self, mf: MemoryFact, ts: str) -> None:
        if not self.memory_path.exists():
            self.memory_path.write_text(
                "# klerk — MEMORY\n\nAppend-only fact log.\n", encoding="utf-8"
            )
        line = f"- [{ts}] ({mf.kind}) {mf.fact}\n"
        with self.memory_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    # ─── RECALL ──────────────────────────────────────────────────────────────
    def recall(self, query: str, k: int = 4) -> list[RecalledFact]:
        """Hybrid (vector + BM25, RRF-fused) recall over `memory_v1`.

        Falls back to vector-only if the BM25 path is unavailable (e.g. the
        FTS index could not be built on a tiny table). Returns scored facts,
        highest first. Empty/missing table → empty list (never raises).
        """
        table = self._open_table_or_none()
        if table is None or table.count_rows() == 0:
            return []

        k_initial = max(k * 4, k)
        qv = embed_query(query)
        try:
            vec_hits = (
                table.search(qv, vector_column_name="vector").limit(k_initial).to_list()
            )
        except Exception:  # noqa: BLE001
            vec_hits = []
        try:
            bm25_hits = table.search(query, query_type="fts").limit(k_initial).to_list()
        except Exception:  # noqa: BLE001 - FTS may be absent on tiny tables
            bm25_hits = []

        by_id: dict[str, dict[str, Any]] = {}
        for hit in vec_hits + bm25_hits:
            by_id.setdefault(hit["fact_id"], hit)

        if not by_id:
            return []

        fused = rrf_by_key([vec_hits, bm25_hits], key="fact_id", k=60)[:k]
        out: list[RecalledFact] = []
        for fact_id, score, _ranks in fused:
            row = by_id[fact_id]
            out.append(
                RecalledFact(
                    fact=row["text"],
                    kind=row.get("kind", "note"),
                    ts=row.get("ts", ""),
                    score=score,
                )
            )
        return out


# ─── PydanticAI extraction ──────────────────────────────────────────────────
_EXTRACT_SYSTEM = """\
You are klerk's memory extractor. Given an assistant turn (what klerk just
told the operator), extract 0 to 3 DURABLE facts worth remembering across
future sessions — stable preferences, decisions, entities, or constraints.

Rules:
  - Only extract facts that will still matter next session. Ignore one-off
    chit-chat, greetings, and anything tied to the current query alone.
  - Phrase each fact as a standalone statement (no pronouns like "it"/"they"
    without an antecedent).
  - `kind` is one of: "preference", "entity", "decision", "constraint", "note".
  - If nothing is worth remembering, return an empty list.
"""


class _MemoryFacts(BaseModel):
    facts: list[MemoryFact] = Field(default_factory=list, max_length=3)


def extract_facts(assistant_turn: str, *, locale: str = "en") -> list[MemoryFact]:
    """Extract 0-3 durable `MemoryFact`s from an assistant turn via PydanticAI.

    LLM-backed and therefore mockable: tests monkeypatch
    `klerk.agent.pai.ask_typed` (or this function directly). Returns at most 3.
    """
    from klerk.agent.pai import ask_typed

    result = ask_typed(
        _MemoryFacts,
        system=_EXTRACT_SYSTEM,
        user=f"LOCALE: {locale}\n\nASSISTANT TURN:\n{assistant_turn}\n\nExtract durable facts.",
        locale=locale,
        max_tokens=512,
    )
    return list(result.facts)[:3]
