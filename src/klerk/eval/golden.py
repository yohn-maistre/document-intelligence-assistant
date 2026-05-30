"""Golden-set loader — reads the brief's evaluation_set.json schema.

The brief specifies the eval format: a JSON file at repo root with 20
items distributed as 8 factual / 5 multi-hop / 3 conflict / 2 Bahasa /
2 trick. Items declare the expected substrings the answer should contain
and the source doc_ids the system was expected to retrieve, plus a
should_say_dont_know flag for the trick subset.

For convenience this loader still supports the older YAML files in
data/golden/ if they exist — that path was klerk's pre-brief shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

Category = Literal["factual", "multi_hop", "conflict", "bahasa", "trick"]


@dataclass
class GoldenItem:
    id: str
    question: str
    locale: str
    category: Category
    expected_answer: str = ""
    expected_substrings: list[str] = field(default_factory=list)
    expected_doc_ids: list[str] = field(default_factory=list)
    should_say_dont_know: bool = False
    notes: str | None = None

    # Backwards-compat alias for the legacy YAML loader's `kind` field.
    @property
    def kind(self) -> str:
        return self.category


def _from_dict(d: dict) -> GoldenItem:
    return GoldenItem(
        id=d["id"],
        question=d["question"],
        locale=d.get("locale", "en"),
        category=d.get("category") or d.get("kind") or "factual",
        expected_answer=d.get("expected_answer", ""),
        expected_substrings=list(d.get("expected_substrings", [])),
        expected_doc_ids=list(d.get("expected_doc_ids", d.get("expected_chunks", []))),
        should_say_dont_know=bool(d.get("should_say_dont_know", False)),
        notes=d.get("notes"),
    )


def load_brief_set(path: Path | None = None) -> list[GoldenItem]:
    """Load the 20-Q evaluation_set.json at the repo root."""
    path = path or Path("evaluation_set.json")
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items_raw = payload.get("items") if isinstance(payload, dict) else payload
    return [_from_dict(d) for d in items_raw]


def load_legacy_yaml(locale: str | None = None) -> list[GoldenItem]:
    """Old YAML files at data/golden/qa_*.yaml — kept for compat."""
    items: list[GoldenItem] = []
    files = sorted(Path("data/golden").glob("qa_*.yaml"))
    for f in files:
        loc_from_name = f.stem.split("_", 1)[-1]
        if locale and loc_from_name != locale:
            continue
        raw = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        for r in raw:
            r = dict(r)
            r.setdefault("locale", loc_from_name)
            items.append(_from_dict(r))
    return items


def load(locale: str | None = None) -> list[GoldenItem]:
    """Unified loader: prefer evaluation_set.json (brief's shape); fall back to YAML."""
    items = load_brief_set()
    if not items:
        items = load_legacy_yaml(locale=locale)
    if locale:
        items = [it for it in items if it.locale == locale]
    return items


def by_category(items: list[GoldenItem]) -> dict[str, list[GoldenItem]]:
    out: dict[str, list[GoldenItem]] = {}
    for it in items:
        out.setdefault(it.category, []).append(it)
    return out
