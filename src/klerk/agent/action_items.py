"""Capability B — Action Item Extractor.

Pulls structured action items (assignee · action · due · priority) out of:
  - a specific doc, by `doc_id`, with chunk-level grounding
  - a free-text snippet (e.g. pasted meeting minutes)

The brief calls out meeting minutes specifically, but the agent is
content-agnostic — any doc with "do X by Y" language works.

The internal pipeline:
  1. If doc_id given, pull every chunk for that doc from LanceDB; otherwise
     treat the input as the entire text.
  2. Send the chunks (with chunk_ids preserved) to Nemotron via a PydanticAI
     `Agent(output_type=ActionExtraction)` asking for action items + per-item
     source_chunk attribution. PydanticAI handles schema prompting + parsing.
  3. The typed result is returned directly; the source field is pinned by the
     caller so the model can't drift it.

Output: `ActionExtraction` Pydantic model (see klerk.agent._models).
"""

from __future__ import annotations

from klerk.agent._models import ActionExtraction
from klerk.agent.pai import ask_typed
from klerk.rag.store import CORPUS_TABLE, open_db

_SYSTEM_PROMPT = """\
You are klerk's action-item extractor. From the source text below, pull
every explicit or implicit action item. An action item is a commitment
that has (at minimum) an owner and a thing to be done.

Output STRICT JSON matching this schema:
{
  "items": [
    {
      "assignee": "<person, role, or team — verbatim from text where possible>",
      "action": "<concise imperative phrasing of what they must do>",
      "due": "<date or deadline phrase if stated, else null>",
      "priority": "low" | "medium" | "high",
      "source_chunk": "<chunk_id of the citation if available, else null>"
    },
    ...
  ],
  "source": "doc:<doc_id>" | "text"
}

Rules:
  - Output ONLY the JSON object. No prose, no markdown fences.
  - If no actionable items are present, return {"items": [], "source": ...}.
  - Priority heuristic:
      "high"   if the source mentions security / compliance / customer
               impact / a deadline in the next 14 days.
      "medium" default.
      "low"    if it's a "nice to have" or "consider doing X".
  - When chunk_ids appear in the input (format [doc_id:n]), reproduce the
    EXACT chunk_id in `source_chunk` for each item you derive from that
    chunk. Otherwise leave `source_chunk` null.
  - Be specific in `action` — "review the Q1 budget variance report" not
    "review the report".
"""


def _doc_chunks(doc_id: str) -> list[tuple[str, str]]:
    """Pull all chunks for `doc_id` from LanceDB. Returns [(chunk_id, text)]."""
    db = open_db()
    if CORPUS_TABLE not in db.list_tables():
        raise RuntimeError(
            "action_items: corpus is empty — run `klerk index build` first."
        )
    table = db.open_table(CORPUS_TABLE).to_pandas()
    rows = table[table["doc_id"] == doc_id]
    if rows.empty:
        raise RuntimeError(f"action_items: no chunks found for doc_id={doc_id!r}")
    return [(r["chunk_id"], r["text"]) for _, r in rows.iterrows()]


def extract(
    *,
    doc_id: str | None = None,
    text: str | None = None,
    locale: str = "en",
) -> ActionExtraction:
    """Extract action items from a doc or raw text. Exactly one of
    doc_id / text is required (the FastAPI layer enforces this)."""
    if doc_id is None and text is None:
        raise ValueError("extract: pass either doc_id or text.")
    if doc_id is not None and text is not None:
        raise ValueError("extract: pass doc_id OR text, not both.")

    if doc_id is not None:
        chunks = _doc_chunks(doc_id)
        body = "\n\n".join(f"[{cid}] {body}" for cid, body in chunks)
        source = f"doc:{doc_id}"
    else:
        body = text or ""
        source = "text"

    user = (
        f"SOURCE: {source}\n"
        f"LOCALE: {locale}\n\n"
        f"TEXT:\n{body}\n\n"
        "Extract action items."
    )

    result = ask_typed(
        ActionExtraction,
        system=_SYSTEM_PROMPT,
        user=user,
        locale=locale,
        max_tokens=1200,
    )
    # Force the source field even if the model fills something different
    return result.model_copy(update={"source": source})
