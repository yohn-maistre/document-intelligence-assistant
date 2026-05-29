"""Golden-set loader — YAML in, validated dataclasses out."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


@dataclass
class GoldenItem:
    id: str
    question: str
    locale: str
    kind: Literal["single-doc", "multi-hop", "crag-trigger"]
    expected_chunks: list[str] = field(default_factory=list)
    expected_substrings: list[str] = field(default_factory=list)


_GOLDEN_DIR = Path("data/golden")


def load(locale: str | None = None) -> list[GoldenItem]:
    """Load all golden items, optionally filtered by locale (`en` | `id`).

    File layout: `data/golden/qa_<locale>.yaml` per language.
    """
    items: list[GoldenItem] = []
    files = sorted(_GOLDEN_DIR.glob("qa_*.yaml"))
    for f in files:
        loc_from_name = f.stem.split("_", 1)[-1]  # "qa_en" -> "en"
        if locale and loc_from_name != locale:
            continue
        raw = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        for r in raw:
            items.append(
                GoldenItem(
                    id=r["id"],
                    question=r["question"],
                    locale=r.get("locale", loc_from_name),
                    kind=r.get("kind", "single-doc"),
                    expected_chunks=list(r.get("expected_chunks", [])),
                    expected_substrings=list(r.get("expected_substrings", [])),
                )
            )
    return items
