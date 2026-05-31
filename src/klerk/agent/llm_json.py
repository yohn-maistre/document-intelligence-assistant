"""Helper: ask the LLM for a JSON object validated against a Pydantic schema.

Pydantic AI's full agent abstraction is overkill for one-shot structured calls.
This helper uses LiteLLM's `response_format={"type": "json_object"}` + Pydantic
validation, with a single retry on validation failure.
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from klerk.llm.router import complete

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> str:
    """Pull a JSON object/array out of a model reply that may be fenced or
    wrapped in reasoning/prose (the Nemotron proxy returns plain text)."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0].strip()
    if not (s.startswith("{") or s.startswith("[")):
        starts = [p for p in (s.find("{"), s.find("[")) if p != -1]
        if starts:
            i = min(starts)
            j = max(s.rfind("}"), s.rfind("]"))
            if j > i:
                s = s[i : j + 1]
    return s or "{}"


def ask_json(
    schema: type[T],
    *,
    system: str,
    user: str,
    locale: str = "en",
    temperature: float = 0.0,
    max_tokens: int | None = 1024,
    retries: int = 1,
) -> T:
    """Call the LLM, parse JSON, validate against `schema`. Retry once on failure."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = complete(
                messages=messages,
                locale=locale,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(_extract_json(content))
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            if attempt < retries:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous reply did not parse as JSON matching the schema. "
                            f"Error: {e}. Reply ONLY with the valid JSON object — no prose, no markdown fences."
                        ),
                    }
                )
                continue
            raise
    raise RuntimeError("unreachable") from last_err
