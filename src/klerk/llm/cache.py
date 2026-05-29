"""LLM cache — two layers, both prod-grade, both bypass when API key absent.

Layer 1: DiskCache for exact-match (SQLite-backed key-value, thread-safe).
Layer 2: LanceDB `llm_cache` table for semantic match (cosine > threshold).

Architecture note: LanceDB is doing double-duty here (corpus retrieval AND
LLM-call caching). One vector primitive, two roles — clean architectural
signal vs. adding Redis/Upstash.

Caller flow inside klerk.llm.router.complete:
    key = make_key(messages, **kwargs)
    if hit := cache_get(messages, key=key):
        return hit
    raw = litellm.completion(...)
    cache_put(messages, key=key, response=raw)
    return raw
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import diskcache as dc
import lancedb
import numpy as np
import pyarrow as pa

from klerk.rag.embed import EMBED_DIM, embed_query

CACHE_TABLE = "llm_cache"
DEFAULT_SIM_THRESHOLD = 0.95


def _diskcache_dir() -> Path:
    p = Path(os.environ.get("KLERK_DISKCACHE_DIR", ".diskcache"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _lancedb_dir() -> Path:
    p = Path(os.environ.get("KLERK_LANCEDB_DIR", ".lancedb"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _semantic_threshold() -> float:
    try:
        return float(os.environ.get("KLERK_SEMANTIC_CACHE_THRESHOLD", DEFAULT_SIM_THRESHOLD))
    except ValueError:
        return DEFAULT_SIM_THRESHOLD


def _semantic_enabled() -> bool:
    return os.environ.get("KLERK_SEMANTIC_CACHE", "1") == "1"


# ─── Cache key ───────────────────────────────────────────────────────────────
def make_key(messages: list[dict], **kwargs: Any) -> str:
    """Deterministic SHA256 over messages + temperature + model + locale + tools shape.

    We deliberately exclude transient fields (timestamps, request IDs); only
    inputs that affect the LLM output go in.
    """
    payload = {
        "messages": messages,
        "temperature": kwargs.get("temperature"),
        "max_tokens": kwargs.get("max_tokens"),
        "model": kwargs.get("model"),
        "locale": kwargs.get("locale"),
        "response_format": kwargs.get("response_format"),
        "tools": kwargs.get("tools"),
        "tool_choice": kwargs.get("tool_choice"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ─── DiskCache (exact-match) ─────────────────────────────────────────────────
def _disk():
    return dc.Cache(str(_diskcache_dir()))


def disk_get(key: str) -> str | None:
    with _disk() as cache:
        return cache.get(key)


def disk_put(key: str, value: str) -> None:
    with _disk() as cache:
        cache[key] = value


# ─── LanceDB semantic cache ──────────────────────────────────────────────────
def _semantic_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("key", pa.string(), nullable=False),
            pa.field("prompt_text", pa.string(), nullable=False),
            pa.field("response_text", pa.string(), nullable=False),
            pa.field("ts", pa.float64(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), EMBED_DIM), nullable=False),
        ]
    )


def _semantic_table():
    db = lancedb.connect(str(_lancedb_dir()))
    if CACHE_TABLE not in db.table_names():
        return db.create_table(CACHE_TABLE, schema=_semantic_schema())
    return db.open_table(CACHE_TABLE)


def _summarise_messages(messages: list[dict]) -> str:
    """Cheap textual digest of messages for embedding (system + user roles only)."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):  # multimodal — flatten text bits
            content = " ".join(
                str(p.get("text", "")) for p in content if isinstance(p, dict)
            )
        if role in ("system", "user"):
            parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def semantic_get(messages: list[dict]) -> str | None:
    if not _semantic_enabled():
        return None
    try:
        table = _semantic_table()
    except Exception:  # noqa: BLE001
        return None
    if table.count_rows() == 0:
        return None
    digest = _summarise_messages(messages)
    if not digest.strip():
        return None
    try:
        vec = embed_query(digest)
        rows = (
            table.search(vec, vector_column_name="vector")
            .limit(1)
            .to_list()
        )
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None
    # LanceDB returns _distance (cosine distance for normalized vectors ≈ 1 - sim)
    distance = rows[0].get("_distance", 1.0)
    similarity = 1.0 - float(distance)
    if similarity >= _semantic_threshold():
        return rows[0]["response_text"]
    return None


def semantic_put(key: str, messages: list[dict], response_text: str) -> None:
    if not _semantic_enabled():
        return
    digest = _summarise_messages(messages)
    if not digest.strip():
        return
    try:
        vec = embed_query(digest)
        table = _semantic_table()
        table.add(
            [
                {
                    "key": key,
                    "prompt_text": digest[:8000],  # cap to keep table light
                    "response_text": response_text,
                    "ts": time.time(),
                    "vector": vec.tolist(),
                }
            ]
        )
    except Exception:  # noqa: BLE001 - cache write must never break a live call
        return


# ─── Public combined API used by the router ──────────────────────────────────
@dataclass
class CacheHit:
    layer: str  # "disk" | "semantic"
    response_text: str


def lookup(messages: list[dict], **kwargs: Any) -> tuple[str, CacheHit | None]:
    """Return (key, optional hit). Caller uses the hit if present, else generates."""
    key = make_key(messages, **kwargs)
    hit = disk_get(key)
    if hit is not None:
        return key, CacheHit(layer="disk", response_text=hit)
    sem = semantic_get(messages)
    if sem is not None:
        return key, CacheHit(layer="semantic", response_text=sem)
    return key, None


def store(key: str, messages: list[dict], response_text: str) -> None:
    """Persist to both layers. Failures are silently swallowed (caching is best-effort)."""
    try:
        disk_put(key, response_text)
    except Exception:  # noqa: BLE001
        pass
    semantic_put(key, messages, response_text)


def cache_stats() -> dict[str, Any]:
    out: dict[str, Any] = {
        "disk_dir": str(_diskcache_dir()),
        "lancedb_dir": str(_lancedb_dir()),
        "semantic_enabled": _semantic_enabled(),
        "semantic_threshold": _semantic_threshold(),
    }
    try:
        with _disk() as c:
            out["disk_entries"] = len(c)
    except Exception:  # noqa: BLE001
        out["disk_entries"] = "?"
    try:
        table = _semantic_table()
        out["semantic_entries"] = table.count_rows()
    except Exception:  # noqa: BLE001
        out["semantic_entries"] = 0
    return out
