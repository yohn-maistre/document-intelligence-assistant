"""Nemotron NIM configuration — isolates any zip-revealed quirks.

If the password-protected NIM zip exposes a custom auth header, endpoint shape,
or non-OpenAI-compatible behavior, contain the change here. The rest of the
codebase calls `klerk.llm.router.complete()` and stays provider-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NemotronConfig:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> NemotronConfig:
        return cls(
            api_key=os.environ.get("NVIDIA_API_KEY", ""),
            base_url=os.environ.get(
                "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"
            ),
            model=os.environ.get("NVIDIA_NIM_MODEL", "nvidia/nemotron-4-340b-instruct"),
        )

    @property
    def litellm_model(self) -> str:
        """LiteLLM uses `openai/<model>` for OpenAI-compatible endpoints."""
        return f"openai/{self.model}"
