"""LanceDB hybrid store — vector + Tantivy BM25 in one table.

One table per corpus split:
  - `corpus` — the working RAG store
  - `llm_cache` — semantic prompt→response cache (separate; written by router)

LanceDB's hybrid API exposes vector + BM25 together with a configurable
reranker. We use it for the initial retrieval pass; downstream BGE-Reranker
takes over for final precision.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
import pyarrow as pa

from klerk.rag.chunker import Chunk
from klerk.rag.embed import EMBED_DIM, embed_passages

CORPUS_TABLE = "corpus"
LLM_CACHE_TABLE = "llm_cache"


def _db_dir() -> Path:
    return Path(os.environ.get("KLERK_LANCEDB_DIR", ".lancedb"))


@dataclass(frozen=True)
class IndexStats:
    table: str
    n_rows: int
    embed_dim: int
    fts_indexed: bool


def _corpus_schema() -> pa.Schema:
    """Frozen schema so reloads across runs are stable."""
    return pa.schema(
        [
            pa.field("chunk_id", pa.string(), nullable=False),  # `<doc_id>:<idx>`
            pa.field("doc_id", pa.string(), nullable=False),
            pa.field("chunk_idx", pa.int32(), nullable=False),
            pa.field("text", pa.string(), nullable=False),
            pa.field("locale", pa.string(), nullable=False),
            pa.field("source", pa.string(), nullable=False),
            pa.field("n_tokens", pa.int32(), nullable=False),
            pa.field(
                "vector",
                pa.list_(pa.float32(), EMBED_DIM),
                nullable=False,
            ),
        ]
    )


def open_db():
    db_dir = _db_dir()
    db_dir.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(db_dir))


def reset_corpus() -> None:
    db = open_db()
    if CORPUS_TABLE in db.table_names():
        db.drop_table(CORPUS_TABLE)


def upsert_chunks(chunks: Iterable[Chunk]) -> int:
    """Embed + insert chunks. Returns count inserted.

    Creates the table (and the FTS index on `text`) on first call.
    """
    chunk_list = list(chunks)
    if not chunk_list:
        return 0

    vectors = embed_passages([c.text for c in chunk_list])
    rows = [
        {
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "chunk_idx": c.chunk_idx,
            "text": c.text,
            "locale": c.locale,
            "source": c.source,
            "n_tokens": c.n_tokens,
            "vector": vectors[i].tolist(),
        }
        for i, c in enumerate(chunk_list)
    ]

    db = open_db()
    if CORPUS_TABLE in db.table_names():
        table = db.open_table(CORPUS_TABLE)
        table.add(rows)
    else:
        table = db.create_table(CORPUS_TABLE, data=rows, schema=_corpus_schema())

    _ensure_fts_index(table)
    return len(rows)


def _ensure_fts_index(table) -> None:
    """Create / refresh the BM25 FTS index on the text column.

    LanceDB's native FTS is used (replaced Tantivy as embedded in May 2026).
    Re-creating is idempotent and cheap on a 25-doc corpus.
    """
    try:
        table.create_fts_index("text", replace=True)
    except Exception:  # noqa: BLE001
        # LanceDB sometimes raises if the index already exists and the table
        # is empty; on a 25-doc corpus this is benign.
        pass


def stats() -> IndexStats | None:
    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        return None
    table = db.open_table(CORPUS_TABLE)
    n_rows = table.count_rows()
    fts_indexed = False
    try:
        # Probe by issuing a tiny FTS query; if it works, we're indexed.
        table.search("klerk_fts_probe", query_type="fts").limit(1).to_list()
        fts_indexed = True
    except Exception:  # noqa: BLE001
        fts_indexed = False
    return IndexStats(table=CORPUS_TABLE, n_rows=n_rows, embed_dim=EMBED_DIM, fts_indexed=fts_indexed)


# ─── Search primitives ────────────────────────────────────────────────────────
def search_vector(query_vec: np.ndarray, *, k: int = 16) -> list[dict[str, Any]]:
    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        return []
    table = db.open_table(CORPUS_TABLE)
    return (
        table.search(query_vec, vector_column_name="vector")
        .limit(k)
        .to_list()
    )


def search_bm25(query: str, *, k: int = 16) -> list[dict[str, Any]]:
    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        return []
    table = db.open_table(CORPUS_TABLE)
    return (
        table.search(query, query_type="fts").limit(k).to_list()
    )
