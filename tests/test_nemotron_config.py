"""NemotronConfig — verifies the password-zip surface (proxy + CF headers).

Tests are env-var-driven; we use monkeypatch to keep them isolated.
"""

from __future__ import annotations

import pytest

from klerk.llm.nemotron import NemotronConfig


def test_primary_env_vars_win(monkeypatch: pytest.MonkeyPatch) -> None:
    """LITELLM_KEY / PROXY_URL / NEMOTRON_MODEL are the new-canonical names."""
    monkeypatch.setenv("LITELLM_KEY", "sk-test-primary")
    monkeypatch.setenv("PROXY_URL", "https://llm-proxy.atlas-horizon.com")
    monkeypatch.setenv("NEMOTRON_MODEL", "nemotron-3-nano-omni")
    monkeypatch.setenv("CF_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_CLIENT_SECRET", "cf-secret")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    cfg = NemotronConfig.from_env()
    assert cfg.api_key == "sk-test-primary"
    assert cfg.base_url == "https://llm-proxy.atlas-horizon.com/v1"
    assert cfg.model == "nemotron-3-nano-omni"
    assert cfg.litellm_model == "openai/nemotron-3-nano-omni"
    assert cfg.cf_headers == {
        "CF-Access-Client-Id": "cf-id",
        "CF-Access-Client-Secret": "cf-secret",
    }


def test_legacy_nvidia_env_vars_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-zip NVIDIA_* names still work for backwards-compat."""
    monkeypatch.delenv("LITELLM_KEY", raising=False)
    monkeypatch.delenv("PROXY_URL", raising=False)
    monkeypatch.delenv("NEMOTRON_MODEL", raising=False)
    monkeypatch.delenv("CF_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "sk-legacy")
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("NVIDIA_NIM_MODEL", "nvidia/nemotron-4-340b-instruct")

    cfg = NemotronConfig.from_env()
    assert cfg.api_key == "sk-legacy"
    assert cfg.base_url == "https://integrate.api.nvidia.com/v1"
    assert cfg.model == "nvidia/nemotron-4-340b-instruct"
    assert cfg.cf_headers == {}  # no CF tokens → empty (skipped in router)


def test_proxy_url_appends_v1_if_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """PROXY_URL bare host gets /v1 appended; already-suffixed URL is left alone."""
    monkeypatch.setenv("LITELLM_KEY", "k")
    monkeypatch.setenv("PROXY_URL", "https://proxy.example.com")
    monkeypatch.delenv("NVIDIA_NIM_BASE_URL", raising=False)
    assert NemotronConfig.from_env().base_url == "https://proxy.example.com/v1"

    monkeypatch.setenv("PROXY_URL", "https://proxy.example.com/v1")
    assert NemotronConfig.from_env().base_url == "https://proxy.example.com/v1"


def test_empty_config_yields_blanks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset key → empty string, never None (router uses it directly)."""
    for var in (
        "LITELLM_KEY",
        "PROXY_URL",
        "NEMOTRON_MODEL",
        "CF_CLIENT_ID",
        "CF_CLIENT_SECRET",
        "NVIDIA_API_KEY",
        "NVIDIA_NIM_BASE_URL",
        "NVIDIA_NIM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = NemotronConfig.from_env()
    assert cfg.api_key == ""
    assert cfg.cf_headers == {}
    # Defaults still resolve — base_url defaults to the disclosed proxy
    assert cfg.base_url == "https://llm-proxy.atlas-horizon.com/v1"
    assert cfg.model == "nemotron-3-nano-omni"


def test_partial_cf_credentials_means_no_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """One CF var set without the other → no headers (proxy would 403 anyway)."""
    monkeypatch.setenv("LITELLM_KEY", "k")
    monkeypatch.setenv("CF_CLIENT_ID", "only-id")
    monkeypatch.delenv("CF_CLIENT_SECRET", raising=False)
    assert NemotronConfig.from_env().cf_headers == {}
