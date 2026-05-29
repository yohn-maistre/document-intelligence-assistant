"""Chunker correctness — no model deps."""

from __future__ import annotations

from klerk.rag.chunker import chunk_text


def _opts(**over):
    base = {"doc_id": "test", "locale": "en", "source": "test.md"}
    base.update(over)
    return base


def test_empty_returns_no_chunks() -> None:
    assert chunk_text("", **_opts()) == []
    assert chunk_text("   \n\n  ", **_opts()) == []


def test_short_text_one_chunk() -> None:
    chunks = chunk_text("This is a small doc.", **_opts())
    assert len(chunks) == 1
    assert chunks[0].chunk_idx == 0
    assert chunks[0].chunk_id == "test:0"


def test_chunk_ids_are_sequential() -> None:
    # Force many windows with tiny max_tokens
    para = "Sentence one. Sentence two. Sentence three. "
    body = para * 50
    chunks = chunk_text(body, max_tokens=30, overlap_tokens=0, **_opts())
    assert len(chunks) > 1
    for i, c in enumerate(chunks):
        assert c.chunk_idx == i
        assert c.chunk_id == f"test:{i}"


def test_overlap_carries_tail() -> None:
    # Three paragraphs, each ~25 tokens; max=30 forces splits with overlap
    paras = ["First paragraph with several words here. " * 5]
    paras.append("Second paragraph different content entirely. " * 5)
    paras.append("Third paragraph more words to fill space. " * 5)
    body = "\n\n".join(paras)
    chunks_with = chunk_text(body, max_tokens=60, overlap_tokens=20, **_opts())
    chunks_without = chunk_text(body, max_tokens=60, overlap_tokens=0, **_opts())
    # Overlap path should produce same-or-more chunks (carries tail into next window)
    assert len(chunks_with) >= len(chunks_without)


def test_metadata_propagation() -> None:
    chunks = chunk_text(
        "Hello dunia.", doc_id="doc7", locale="id", source="/tmp/x.md"
    )
    assert chunks[0].doc_id == "doc7"
    assert chunks[0].locale == "id"
    assert chunks[0].source == "/tmp/x.md"
    assert chunks[0].n_tokens > 0
