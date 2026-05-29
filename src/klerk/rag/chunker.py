"""Recursive token-aware chunker — splits on natural boundaries, then by size.

The cascade tries paragraph breaks first, then sentence breaks, then hard token
windows. Output chunks carry their source doc_id + position so citations can
reference `[doc_id:chunk_idx]` end-to-end.

Token counts use tiktoken (cl100k_base) — close enough to most modern LLMs for
sizing purposes; we don't claim exact NIM token equivalence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Chunk:
    doc_id: str
    chunk_idx: int
    text: str
    locale: str
    n_tokens: int
    source: str  # original file path as string

    @property
    def chunk_id(self) -> str:
        """`<doc_id>:<chunk_idx>` — used in citations."""
        return f"{self.doc_id}:{self.chunk_idx}"


@lru_cache(maxsize=1)
def _tokenizer_backend() -> tuple[str, object | None]:
    """Pick the best tokenizer available, with graceful fallback.

    Priority:
      1. tiktoken cl100k_base (best fidelity to OpenAI-family models)
      2. transformers AutoTokenizer for BGE-M3 (already loaded for embeddings)
      3. char-heuristic (~4 chars / token; rough but adequate for chunk sizing)

    Returns (backend_name, encoder_or_None). Encoder is None for the
    char-heuristic path.
    """
    try:
        import tiktoken

        return ("tiktoken", tiktoken.get_encoding("cl100k_base"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", use_fast=True)
        return ("transformers", tok)
    except Exception:  # noqa: BLE001
        pass
    return ("char_heuristic", None)


def _count(text: str) -> int:
    name, enc = _tokenizer_backend()
    if name == "tiktoken":
        return len(enc.encode(text))  # type: ignore[union-attr]
    if name == "transformers":
        return len(enc.encode(text, add_special_tokens=False))  # type: ignore[union-attr]
    # char heuristic: ~4 chars/token; slightly punitive for CJK / scripts is OK
    return max(1, (len(text) + 3) // 4)


_PARA_RE = re.compile(r"\n\s*\n+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\n+")


def chunk_text(
    text: str,
    *,
    doc_id: str,
    locale: str,
    source: str,
    max_tokens: int = 384,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Recursive chunker. Returns ordered, indexed chunks for one doc.

    Strategy:
      1. Split on paragraph breaks.
      2. Pack paragraphs into windows up to max_tokens.
      3. If a paragraph itself > max_tokens, split on sentence boundaries.
      4. If a sentence itself > max_tokens, hard-split by token count.

    Overlap is added by carrying the tail of the previous window into the next.
    """
    if not text.strip():
        return []

    # First split on paragraph boundaries (keeps semantic units together)
    paragraphs = [p.strip() for p in _PARA_RE.split(text) if p.strip()]

    raw_pieces: list[str] = []
    for para in paragraphs:
        if _count(para) <= max_tokens:
            raw_pieces.append(para)
            continue
        # Paragraph too big — split on sentences
        sentences = _split_sentences(para)
        for sent in sentences:
            if _count(sent) <= max_tokens:
                raw_pieces.append(sent)
            else:
                raw_pieces.extend(_hard_split(sent, max_tokens))

    # Now pack pieces into windows
    windows: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for piece in raw_pieces:
        piece_tokens = _count(piece)
        if current and current_tokens + piece_tokens > max_tokens:
            windows.append("\n\n".join(current))
            # Build overlap: keep tail pieces until overlap budget is filled
            if overlap_tokens > 0:
                tail: list[str] = []
                tail_tokens = 0
                for p in reversed(current):
                    pt = _count(p)
                    if tail_tokens + pt > overlap_tokens:
                        break
                    tail.insert(0, p)
                    tail_tokens += pt
                current = list(tail)
                current_tokens = tail_tokens
            else:
                current = []
                current_tokens = 0
        current.append(piece)
        current_tokens += piece_tokens

    if current:
        windows.append("\n\n".join(current))

    return [
        Chunk(
            doc_id=doc_id,
            chunk_idx=i,
            text=w,
            locale=locale,
            n_tokens=_count(w),
            source=source,
        )
        for i, w in enumerate(windows)
    ]


def _split_sentences(text: str) -> list[str]:
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Last-resort: split by token count when no natural break helps."""
    enc = _encoder()
    tokens = enc.encode(text)
    pieces: list[str] = []
    for start in range(0, len(tokens), max_tokens):
        slice_ = tokens[start : start + max_tokens]
        pieces.append(enc.decode(slice_))
    return pieces
