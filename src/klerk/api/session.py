"""Multi-turn chat memory — SessionStore + sliding-window compaction.

Each chat session is a JSONL file at `.klerk/sessions/{session_id}.jsonl`,
one line per turn: `{"role": "user"|"assistant", "content": ..., "ts": ...}`.

`build_prompt_history` turns a session into a bounded message list for the
orchestrator:
  - the last `keep_verbatim` turns (default 3 user+assistant exchanges) are
    kept word-for-word
  - everything older is compacted into a single summary system message via a
    small Nemotron call ("summarise in <=200 tokens, preserve entities and
    decisions"), so long sessions stay within the 16K token budget
  - the summary is cached by `(session_id, last_summarised_turn_index)` so a
    session that keeps growing only re-summarises the newly-aged-out turns

The token budget is enforced as a coarse char/4 heuristic — we don't pull in
a tokenizer on the hot path; the summary call is the real bound.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TOKEN_BUDGET = 16_000
DEFAULT_KEEP_VERBATIM = 3  # exchanges (user+assistant pairs) kept verbatim
_SUMMARY_MAX_TOKENS = 200


def sessions_dir() -> Path:
    """Resolved at call time so KLERK_STATE_DIR overrides apply per-test."""
    p = Path(os.environ.get("KLERK_STATE_DIR", ".klerk")) / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _session_path(session_id: str) -> Path:
    # Guard against path traversal — session ids are opaque tokens.
    safe = session_id.replace("/", "_").replace("..", "_")
    return sessions_dir() / f"{safe}.jsonl"


@dataclass
class Turn:
    role: str       # "user" | "assistant"
    content: str
    ts: float

    def to_message(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class SessionStore:
    """JSONL-backed per-session turn log + sliding-window prompt assembly."""

    def __init__(
        self,
        *,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        keep_verbatim: int = DEFAULT_KEEP_VERBATIM,
    ) -> None:
        self.token_budget = token_budget
        self.keep_verbatim = keep_verbatim
        # in-process summary cache: (session_id, last_summarised_idx) -> summary
        self._summary_cache: dict[tuple[str, int], str] = {}

    # ── persistence ──────────────────────────────────────────────────────────
    def append(self, session_id: str, role: str, content: str) -> Turn:
        turn = Turn(role=role, content=content, ts=time.time())
        path = _session_path(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"role": role, "content": content, "ts": turn.ts}) + "\n")
        return turn

    def load(self, session_id: str) -> list[Turn]:
        path = _session_path(session_id)
        if not path.exists():
            return []
        turns: list[Turn] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                turns.append(Turn(role=d["role"], content=d["content"], ts=d.get("ts", 0.0)))
            except (json.JSONDecodeError, KeyError):
                continue
        return turns

    def exists(self, session_id: str) -> bool:
        return _session_path(session_id).exists()

    def recent_sessions(self, limit: int = 5) -> list[str]:
        """Session ids, most-recently-modified first."""
        paths = sorted(
            sessions_dir().glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [p.stem for p in paths[:limit]]

    # ── prompt assembly ──────────────────────────────────────────────────────
    def build_prompt_history(
        self,
        session_id: str,
        *,
        summariser=None,
    ) -> list[dict[str, str]]:
        """Assemble a bounded message history for the orchestrator.

        Keeps the last `keep_verbatim` exchanges verbatim; older turns are
        compacted into one summary system message. `summariser` is an optional
        `Callable[[str], str]` (injected in tests); defaults to a small
        Nemotron call.
        """
        turns = self.load(session_id)
        if not turns:
            return []

        verbatim_count = self.keep_verbatim * 2  # user+assistant per exchange
        if len(turns) <= verbatim_count:
            return [t.to_message() for t in turns]

        older = turns[:-verbatim_count]
        recent = turns[-verbatim_count:]
        last_summarised_idx = len(older)  # number of turns folded into the summary

        cache_key = (session_id, last_summarised_idx)
        summary = self._summary_cache.get(cache_key)
        if summary is None:
            summary = self._summarise(older, summariser=summariser)
            self._summary_cache[cache_key] = summary

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": f"Summary of earlier conversation:\n{summary}",
            }
        ]
        messages.extend(t.to_message() for t in recent)
        return self._enforce_budget(messages)

    def _enforce_budget(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Drop oldest non-system messages until under the token budget."""
        def total() -> int:
            return sum(_approx_tokens(m["content"]) for m in messages)

        # Never drop the leading summary system message; trim from the front of
        # the verbatim tail instead.
        head = messages[:1] if messages and messages[0]["role"] == "system" else []
        tail = messages[len(head):]
        while tail and _approx_tokens(head[0]["content"] if head else "") + sum(
            _approx_tokens(m["content"]) for m in tail
        ) > self.token_budget:
            tail.pop(0)
        return head + tail

    def _summarise(self, turns: list[Turn], *, summariser=None) -> str:
        transcript = "\n".join(f"{t.role}: {t.content}" for t in turns)
        if summariser is not None:
            return summariser(transcript)
        return self._nemotron_summary(transcript)

    def _nemotron_summary(self, transcript: str) -> str:
        """Default summariser: one small Nemotron call. Failures degrade to a
        truncated transcript so chat never breaks on summary errors."""
        try:
            from klerk.llm.router import complete

            resp = complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the conversation so far in at most "
                            f"{_SUMMARY_MAX_TOKENS} tokens. Preserve named "
                            "entities, decisions, and any unresolved questions. "
                            "Output prose, no preamble."
                        ),
                    },
                    {"role": "user", "content": transcript},
                ],
                temperature=0.0,
                max_tokens=_SUMMARY_MAX_TOKENS,
            )
            return (resp.choices[0].message.content or "").strip() or transcript[:800]
        except Exception:  # noqa: BLE001 - summary must never break the chat
            return transcript[:800]


# Module-level default store so callers share one summary cache.
_store: SessionStore | None = None


def get_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
