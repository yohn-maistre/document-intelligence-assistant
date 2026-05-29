"""Sanity: every top-level klerk subpackage imports without LLM credentials."""

from __future__ import annotations


def test_root_import() -> None:
    import klerk

    assert klerk.__version__


def test_cli_import() -> None:
    from klerk.cli import main

    assert main.app is not None


def test_llm_router_import() -> None:
    from klerk.llm import nemotron, router

    cfg = nemotron.NemotronConfig.from_env()
    assert cfg.litellm_model.startswith("openai/")
    assert callable(router.complete)


def test_obs_phoenix_import() -> None:
    from klerk.obs import phoenix

    # Don't actually launch; just confirm the symbol exists.
    assert callable(phoenix.launch)
    assert callable(phoenix.instrument_litellm)


def test_subpackages_import() -> None:
    for mod in ("agent", "rag", "drive", "parse", "synth", "eval", "studio", "mcp", "api"):
        __import__(f"klerk.{mod}")
