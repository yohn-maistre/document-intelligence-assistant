"""LiteLLM SDK wrapper — single entry point for all Python-side LLM traffic.

Pi handles its own LLM calls via OpenAI-compat directly. Everything else in
klerk (proposal pipeline, KG extraction, judges, eval rubric, FAQ builder)
calls through here so we get one place to add fallbacks, cost tracking, and
cache wiring.
"""

from __future__ import annotations

import os
from typing import Any

import litellm

from klerk.llm.nemotron import NemotronConfig


def _bahasa_model() -> str:
    qwen = os.environ.get("KLERK_QWEN_MODEL", "qwen/qwen3-235b-instruct")
    return f"openai/{qwen}"


def _select_model(locale: str) -> tuple[str, str]:
    """Return (litellm_model, base_url) for the given locale."""
    cfg = NemotronConfig.from_env()
    if locale == "id":
        return _bahasa_model(), os.environ.get("KLERK_QWEN_BASE_URL", cfg.base_url)
    return cfg.litellm_model, cfg.base_url


def complete(
    messages: list[dict[str, Any]],
    *,
    locale: str = "en",
    temperature: float = 0.0,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> Any:
    """Synchronous chat completion through LiteLLM.

    Returns the LiteLLM response object. Caller pulls `.choices[0].message`.
    """
    cfg = NemotronConfig.from_env()
    model, base_url = _select_model(locale)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_base": base_url,
        "api_key": cfg.api_key,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools is not None:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

    return litellm.completion(**kwargs)
