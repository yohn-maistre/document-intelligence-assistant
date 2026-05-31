"""LiteLLM SDK wrapper — single entry point for all Python-side LLM traffic.

Pi handles its own LLM calls via OpenAI-compat directly. The cached,
locale-routed Python LLM traffic (doc-writer, conflict graph, judges, eval
rubric, FAQ builder) calls through here. The three one-shot typed agents
(action_items, kg_extract, contradiction.judge_pair) route via PydanticAI in
klerk.agent.pai — which reuses this module's `_select_model` for locale-aware
routing but bypasses the cache layers (see pai.py for the rationale).

Cache integration: on every call we check DiskCache (exact match) then
LanceDB `llm_cache` table (semantic match, cosine > threshold). Hits return
a synthetic LiteLLM-shaped response so callers don't need to special-case it.
Misses hit Nemotron via LiteLLM and the response is stored in both layers.

Cache layers can be bypassed for one call with `use_cache=False` (used by
the smoke verb to force a live round-trip).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import litellm

from klerk.llm.cache import lookup, store
from klerk.llm.nemotron import NemotronConfig


def _select_model(locale: str) -> tuple[str, str]:
    """Return (litellm_model, base_url) for the given locale.

    Honest note about --locale id: the disclosed Nemotron proxy is
    single-model (`nemotron-3-nano-omni`); there's no separate Bahasa-tuned
    endpoint here. If the operator sets KLERK_QWEN_BASE_URL + KLERK_QWEN_MODEL
    pointing at a different proxy (e.g. the local llama.cpp from
    scripts/setup-local-llm.sh), we route there. Otherwise --locale id falls
    through to the same nemotron-3-nano-omni model, which is multilingual.
    """
    cfg = NemotronConfig.from_env()
    if locale == "id" and os.environ.get("KLERK_QWEN_BASE_URL"):
        bahasa_model = os.environ.get("KLERK_QWEN_MODEL", "qwen/qwen3-235b-instruct")
        bahasa_base = os.environ["KLERK_QWEN_BASE_URL"].rstrip("/")
        if not bahasa_base.endswith("/v1"):
            bahasa_base += "/v1"
        return f"openai/{bahasa_model}", bahasa_base
    return cfg.litellm_model, cfg.base_url


# ─── Synthetic response for cache hits ───────────────────────────────────────
@dataclass
class _SyntheticMessage:
    content: str
    role: str = "assistant"


@dataclass
class _SyntheticChoice:
    message: _SyntheticMessage
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class CachedResponse:
    """Subset of LiteLLM ModelResponse, enough for `.choices[0].message.content`."""

    choices: list[_SyntheticChoice]
    cached: bool = True
    cache_layer: str | None = None

    @classmethod
    def from_text(cls, text: str, *, layer: str) -> CachedResponse:
        return cls(
            choices=[_SyntheticChoice(message=_SyntheticMessage(content=text))],
            cache_layer=layer,
        )


def complete(
    messages: list[dict[str, Any]],
    *,
    locale: str = "en",
    temperature: float = 0.0,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    use_cache: bool = True,
) -> Any:
    """Chat completion through LiteLLM, with two-layer cache.

    Returns either a LiteLLM ModelResponse or a CachedResponse — both expose
    `.choices[0].message.content` identically.
    """
    cfg = NemotronConfig.from_env()
    model, base_url = _select_model(locale)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_base": base_url,
        "api_key": cfg.api_key,
        "temperature": temperature,
        "locale": locale,
    }
    # Cloudflare Access headers (from the password-zip config). LiteLLM passes
    # `extra_headers` through to the underlying HTTP call.
    cf = cfg.cf_headers
    if cf:
        kwargs["extra_headers"] = cf
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools is not None:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

    # Cache lookup (messages is already in kwargs — don't pass it twice)
    cache_key: str | None = None
    if use_cache:
        cache_key, hit = lookup(**kwargs)
        if hit is not None:
            return CachedResponse.from_text(hit.response_text, layer=hit.layer)

    # Live call (locale isn't a LiteLLM kwarg, pop it before passing through)
    live_kwargs = {k: v for k, v in kwargs.items() if k != "locale"}
    response = litellm.completion(**live_kwargs)

    if use_cache and cache_key is not None:
        try:
            text = response.choices[0].message.content or ""
            store(cache_key, messages, text)
        except Exception:  # noqa: BLE001 - cache write never breaks a call
            pass
    return response
