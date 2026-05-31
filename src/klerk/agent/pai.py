"""PydanticAI bridge — typed one-shot structured output via the Nemotron proxy.

`ask_json` (klerk.agent.llm_json) routes through klerk.llm.router and the
two-layer cache; it's the right tool for the multi-stage flows (doc_writer,
conflict graph) where caching and locale routing pull their weight.

This module is the PydanticAI equivalent for the three *one-shot typed
agents* — action_items, kg_extract, contradiction.judge_pair — where a clean
`Agent(output_type=Model)` boundary beats hand-rolled JSON parsing. It builds
an `OpenAIModel` pointed at the same Nemotron proxy, with the Cloudflare
Access headers baked into the httpx client and locale-aware model selection
reused from the router.

Trade-off (documented): the PydanticAI path uses its own OpenAI client, so it
does NOT hit klerk's DiskCache/LanceDB cache layers. That's acceptable for
these three agents — they run over fresh per-chunk / per-pair inputs where
cache hit rates are low anyway — and we keep the cached `ask_json` path intact
for everything else.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from klerk.llm.nemotron import NemotronConfig
from klerk.llm.router import _select_model

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=4)
def _model_for(locale: str):
    """Build (and cache) a PydanticAI OpenAIModel bound to the Nemotron proxy.

    Cached per locale because `_select_model` may route `id` to a different
    base_url/model when KLERK_QWEN_BASE_URL is set.
    """
    import httpx
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    cfg = NemotronConfig.from_env()
    litellm_model, base_url = _select_model(locale)
    # `_select_model` returns LiteLLM's `openai/<model>` form; PydanticAI wants
    # the bare model name (the OpenAIProvider supplies the openai/ transport).
    model_name = litellm_model.split("/", 1)[-1]

    headers = cfg.cf_headers or None
    http_client = httpx.AsyncClient(headers=headers) if headers else httpx.AsyncClient()
    provider = OpenAIProvider(
        base_url=base_url,
        api_key=cfg.api_key or "api-key-not-set",
        http_client=http_client,
    )
    return OpenAIModel(model_name, provider=provider)


def ask_typed(
    schema: type[T],
    *,
    system: str,
    user: str,
    locale: str = "en",
    temperature: float = 0.0,
    max_tokens: int | None = 1024,
    retries: int = 1,
) -> T:
    """PydanticAI equivalent of `ask_json`: returns a validated `schema` instance.

    Same call shape as `ask_json` so call-sites migrate with a one-line swap.
    PydanticAI handles the JSON-schema prompting, parsing, and validation
    retry internally (`retries`), raising on unrecoverable failure.
    """
    from pydantic_ai import Agent
    from pydantic_ai.settings import ModelSettings

    settings = ModelSettings(temperature=temperature)
    if max_tokens is not None:
        settings["max_tokens"] = max_tokens

    agent = Agent(
        _model_for(locale),
        output_type=schema,
        system_prompt=system,
        retries=retries,
        model_settings=settings,
    )
    result = agent.run_sync(user)
    return result.output
