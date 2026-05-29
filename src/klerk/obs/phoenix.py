"""Arize Phoenix init — SQLite-backed, OpenInference / OpenTelemetry tracing.

`launch()` boots the local Phoenix UI on PHOENIX_PORT (default 6006). Traces
persist to PHOENIX_WORKING_DIR (default `.phoenix/`) and survive restarts.
The Studio TUI's Trace panel reads from this SQLite directly.
"""

from __future__ import annotations

import os
from pathlib import Path


def launch(*, open_browser: bool = False) -> str:
    """Launch the embedded Phoenix UI. Returns the URL."""
    import phoenix as px

    working_dir = Path(os.environ.get("PHOENIX_WORKING_DIR", ".phoenix"))
    working_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PHOENIX_WORKING_DIR"] = str(working_dir.resolve())

    session = px.launch_app()
    url = session.url
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    return url


def instrument_litellm() -> None:
    """Wire OpenInference instrumentation for LiteLLM calls.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    try:
        from openinference.instrumentation.litellm import LiteLLMInstrumentor
    except ImportError:
        return
    LiteLLMInstrumentor().instrument()
