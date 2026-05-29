"""Corpus Learning Agent — auto-FAQ generation.

For each indexed doc (or doc-group), the agent:
  1. Reads representative chunks
  2. Proposes the most useful questions a reader would ask
  3. Answers them via the same CRAG-lite loop with citations
  4. Emits a Markdown FAQ to `data/output/faq.md`

Result: a self-curated FAQ that mirrors what a new joiner would actually want
to know, with citations into the underlying corpus.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from klerk.agent.crag import ask as crag_ask
from klerk.agent.llm_json import ask_json
from klerk.rag.store import CORPUS_TABLE, open_db


# ─── Question proposer schema (local to this module) ─────────────────────────
class ProposedQuestions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=10)


_PROPOSER_PROMPT = """\
You are designing an FAQ for newcomers to a corpus of documents. Given a set of
representative passages from one document (or a tight thematic group), propose
3 to 6 distinct, high-value questions a reader would actually ask.

Rules:
- Questions must be answerable from the passages provided.
- Avoid trivia. Aim for "what changes my understanding."
- Match the dominant language of the passages (en or id).
- Each question stands alone (no anaphora to earlier ones).

Return JSON: {"questions": ["...", "..."]}
"""


@dataclass
class FaqEntry:
    doc_id: str
    question: str
    answer: str
    citations: list[str]
    confidence: float
    locale: str


def _doc_groups() -> dict[str, list[dict]]:
    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        raise RuntimeError("faq.build: no corpus — run `klerk index build` first.")
    rows = db.open_table(CORPUS_TABLE).to_pandas().to_dict("records")
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_doc[r["doc_id"]].append(r)
    for doc_id in by_doc:
        by_doc[doc_id].sort(key=lambda r: r["chunk_idx"])
    return dict(by_doc)


def propose_questions(doc_id: str, chunks: list[dict]) -> ProposedQuestions:
    locale = chunks[0].get("locale", "en") if chunks else "en"
    body = "\n\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks[:6])
    user = f"DOC_ID: {doc_id}\nPASSAGES:\n{body}"
    return ask_json(
        ProposedQuestions,
        system=_PROPOSER_PROMPT,
        user=user,
        locale=locale,
        max_tokens=600,
    )


def build(*, per_doc_q_cap: int = 5) -> list[FaqEntry]:
    """Generate the FAQ across every doc in the corpus.

    `per_doc_q_cap` clamps the question count per doc to avoid runaway cost
    on large corpora.
    """
    groups = _doc_groups()
    entries: list[FaqEntry] = []
    for doc_id, chunks in groups.items():
        if not chunks:
            continue
        try:
            proposed = propose_questions(doc_id, chunks)
        except Exception:  # noqa: BLE001 - one bad doc shouldn't kill the FAQ
            continue
        for q in proposed.questions[:per_doc_q_cap]:
            locale = chunks[0].get("locale", "en")
            try:
                trace = crag_ask(q, locale=locale, k_final=6)
            except Exception:  # noqa: BLE001
                continue
            entries.append(
                FaqEntry(
                    doc_id=doc_id,
                    question=q,
                    answer=trace.answer.answer,
                    citations=list(trace.answer.citations),
                    confidence=trace.answer.confidence,
                    locale=locale,
                )
            )
    return entries


def render_markdown(entries: list[FaqEntry]) -> str:
    if not entries:
        return "# FAQ\n\n(no entries — run `klerk index build` and `klerk faq build`)\n"
    out: list[str] = ["# klerk auto-FAQ", ""]
    by_doc: dict[str, list[FaqEntry]] = defaultdict(list)
    for e in entries:
        by_doc[e.doc_id].append(e)
    for doc_id in sorted(by_doc):
        out.append(f"## {doc_id}")
        out.append("")
        for e in by_doc[doc_id]:
            out.append(f"### Q. {e.question}")
            out.append("")
            out.append(e.answer)
            out.append("")
            if e.citations:
                out.append(f"*citations: {', '.join(e.citations)} · confidence: {e.confidence:.2f}*")
                out.append("")
    return "\n".join(out)


def save(entries: list[FaqEntry]) -> Path:
    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "faq.md"
    path.write_text(render_markdown(entries), encoding="utf-8")
    return path
