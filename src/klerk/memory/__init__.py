"""klerk long-term memory (Hermes trio): SOUL.md + MEMORY.md + LanceDB recall.

Public API:
  - `MemoryStore`        — the trio, backed by a base dir (tests pass a tmp dir).
  - `MemoryFact`         — a durable fact (Pydantic model).
  - `RecalledFact`       — a scored recall result.
  - `extract_facts`      — PydanticAI extraction of 0-3 facts from a turn.
  - `recall`/`read_soul`/`save` — module-level conveniences over a default store.

The convenience functions construct a `MemoryStore` on a default base dir
(`KLERK_MEMORY_DIR` / XDG / ~/.local/share). For isolated tests, instantiate
`MemoryStore(base_dir=...)` directly.
"""

from __future__ import annotations

from klerk.memory.store import (
    MemoryFact,
    MemoryStore,
    RecalledFact,
    extract_facts,
)

__all__ = [
    "MemoryStore",
    "MemoryFact",
    "RecalledFact",
    "extract_facts",
    "recall",
    "read_soul",
    "save",
]


def _store() -> MemoryStore:
    return MemoryStore()


def recall(query: str, k: int = 4) -> list[RecalledFact]:
    """Recall up to `k` facts from the default memory store."""
    return _store().recall(query, k=k)


def read_soul() -> str:
    """Return SOUL.md from the default memory store (seeded on first run)."""
    return _store().read_soul()


def save(fact: str | MemoryFact) -> MemoryFact:
    """Save a fact into the default memory store."""
    return _store().save(fact)
