"""Nemotron config — isolates the password-zip surface in one file.

The proxy disclosed in the password-protected package is NOT the public
NIM endpoint. It's a **private Cloudflare-tunneled LiteLLM proxy**:

  - Base URL: https://llm-proxy.atlas-horizon.com/v1  (default; overridable)
  - Auth:     Authorization: Bearer <LITELLM_KEY>
              + CF-Access-Client-Id     <CF_CLIENT_ID>
              + CF-Access-Client-Secret <CF_CLIENT_SECRET>
  - Models:   nemotron-3-nano-omni (single-model key; 90-day validity)

This module surfaces all four secrets + the model name, and the Cloudflare
headers as a property so the router can pass them via LiteLLM's
`extra_headers` parameter on every call. Everything else in klerk calls
through `klerk.llm.router.complete()` and stays provider-agnostic.

Backwards-compat: the NVIDIA_API_KEY / NVIDIA_NIM_BASE_URL / NVIDIA_NIM_MODEL
env vars from the pre-zip plan are still honored as fallbacks so any
existing `.env` files keep working.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NemotronConfig:
    api_key: str
    base_url: str
    model: str
    cf_client_id: str
    cf_client_secret: str

    @classmethod
    def from_env(cls) -> NemotronConfig:
        # Primary env vars (per the zip's config.env); fall back to the
        # pre-zip NVIDIA_* names so old .env files still work.
        api_key = os.environ.get("LITELLM_KEY") or os.environ.get("NVIDIA_API_KEY", "")
        base_url = (
            os.environ.get("PROXY_URL")
            or os.environ.get("NVIDIA_NIM_BASE_URL")
            or "https://llm-proxy.atlas-horizon.com"
        )
        # PROXY_URL in the zip is the host; we append /v1 if missing.
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        model = os.environ.get("NEMOTRON_MODEL") or os.environ.get(
            "NVIDIA_NIM_MODEL", "nemotron-3-nano-omni"
        )
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            cf_client_id=os.environ.get("CF_CLIENT_ID", ""),
            cf_client_secret=os.environ.get("CF_CLIENT_SECRET", ""),
        )

    @property
    def litellm_model(self) -> str:
        """LiteLLM uses `openai/<model>` for OpenAI-compatible endpoints."""
        return f"openai/{self.model}"

    @property
    def cf_headers(self) -> dict[str, str]:
        """Cloudflare Access service-token headers, or empty if not configured."""
        if self.cf_client_id and self.cf_client_secret:
            return {
                "CF-Access-Client-Id": self.cf_client_id,
                "CF-Access-Client-Secret": self.cf_client_secret,
            }
        return {}
