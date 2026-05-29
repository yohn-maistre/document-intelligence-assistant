"""Anomaly detection — surface outlier docs that don't fit the corpus pattern.

Method:
  1. Compute the corpus centroid (mean of all chunk embeddings).
  2. For each doc, compute the cosine distance from the centroid (averaged
     across its chunks).
  3. Items > 2σ from the mean distance are flagged as outliers.
  4. For each flagged doc, ask the LLM to briefly justify why it stands out
     (a short paragraph that the operator can use to triage).

Use case: an HR policy folder receives a stray legal contract; the BPO team
wants it routed to a different reviewer. Anomaly scan flags it; the
justification tells the operator why.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from klerk.llm.router import complete
from klerk.rag.store import CORPUS_TABLE, open_db


@dataclass
class AnomalyHit:
    doc_id: str
    mean_distance: float
    z_score: float
    n_chunks: int
    justification: str


_JUSTIFY_PROMPT = """\
A document was flagged as an outlier within a corpus. Given a short sample
from the document and a brief description of the corpus theme, write a
one-paragraph (≤80 words) justification of WHY this document stands out.

Be specific. Reference content. Don't restate the metric. If the document
genuinely doesn't seem out of place, say so explicitly.
"""


def _load_corpus_with_vectors() -> list[dict]:
    db = open_db()
    if CORPUS_TABLE not in db.table_names():
        raise RuntimeError("anomaly.scan: no corpus — run `klerk index build` first.")
    rows = db.open_table(CORPUS_TABLE).to_pandas().to_dict("records")
    return rows


def _doc_centroids(rows: list[dict]) -> dict[str, np.ndarray]:
    """Mean embedding per doc."""
    by_doc: dict[str, list[np.ndarray]] = defaultdict(list)
    for r in rows:
        vec = np.asarray(r["vector"], dtype=np.float32)
        by_doc[r["doc_id"]].append(vec)
    return {doc: np.mean(vecs, axis=0) for doc, vecs in by_doc.items()}


def _justify(doc_id: str, sample_text: str, theme: str, locale: str = "en") -> str:
    user = (
        f"DOC_ID: {doc_id}\n"
        f"CORPUS THEME (auto-detected): {theme}\n"
        f"SAMPLE FROM DOCUMENT:\n{sample_text[:1200]}"
    )
    try:
        response = complete(
            messages=[
                {"role": "system", "content": _JUSTIFY_PROMPT},
                {"role": "user", "content": user},
            ],
            locale=locale,
            temperature=0.1,
            max_tokens=200,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        return f"(justification unavailable: {type(e).__name__}: {e})"


def scan(*, sigma: float = 2.0, locale: str = "en") -> list[AnomalyHit]:
    """Find outlier docs > `sigma` σ from the corpus centroid in cosine distance.

    Empty corpora or <3 docs → no anomalies (statistics meaningless).
    """
    rows = _load_corpus_with_vectors()
    if not rows:
        return []
    centroids = _doc_centroids(rows)
    if len(centroids) < 3:
        return []

    # Corpus centroid (vectors are L2-normalized so cosine sim = dot)
    all_centroids = np.stack(list(centroids.values()))
    corpus_centroid = np.mean(all_centroids, axis=0)
    corpus_centroid /= np.linalg.norm(corpus_centroid) or 1.0

    distances: dict[str, float] = {}
    for doc_id, c in centroids.items():
        c_norm = c / (np.linalg.norm(c) or 1.0)
        distances[doc_id] = 1.0 - float(np.dot(c_norm, corpus_centroid))

    dist_values = np.array(list(distances.values()))
    mu = float(np.mean(dist_values))
    sigma_val = float(np.std(dist_values)) or 1.0

    # Auto-detect a one-line corpus theme via the most-central doc's title-like preview
    central_doc = min(distances, key=lambda d: distances[d])
    central_rows = [r for r in rows if r["doc_id"] == central_doc]
    theme_preview = central_rows[0]["text"][:200] if central_rows else "(unknown)"
    theme = f"Most central doc looks like: {theme_preview}"

    hits: list[AnomalyHit] = []
    for doc_id, dist in distances.items():
        z = (dist - mu) / sigma_val
        if z >= sigma:
            doc_rows = [r for r in rows if r["doc_id"] == doc_id]
            sample = doc_rows[0]["text"] if doc_rows else ""
            justification = _justify(doc_id, sample, theme, locale=locale)
            hits.append(
                AnomalyHit(
                    doc_id=doc_id,
                    mean_distance=dist,
                    z_score=z,
                    n_chunks=len(doc_rows),
                    justification=justification,
                )
            )
    hits.sort(key=lambda h: h.z_score, reverse=True)
    return hits


def render_report(hits: list[AnomalyHit]) -> str:
    if not hits:
        return "# Anomaly report\n\nNo outliers detected (or corpus too small for statistics).\n"
    out = ["# Anomaly report", ""]
    out.append(f"Found {len(hits)} outlier doc(s).")
    out.append("")
    for h in hits:
        out.append(f"## {h.doc_id}")
        out.append("")
        out.append(f"- z-score: **{h.z_score:.2f}** (mean cosine distance: {h.mean_distance:.4f})")
        out.append(f"- chunks: {h.n_chunks}")
        out.append("")
        out.append(f"> {h.justification}")
        out.append("")
    return "\n".join(out)


def save_report(hits: list[AnomalyHit]) -> Path:
    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "anomalies.md"
    path.write_text(render_report(hits), encoding="utf-8")
    return path
