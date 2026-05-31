#!/usr/bin/env bash
# klerk container entrypoint — runs the two surfaces concurrently under tini.
# tini is PID-1 (Dockerfile ENTRYPOINT) so signals + zombie reaping are handled.
# `wait -n` exits as soon as EITHER process dies, so a crash takes the whole
# container down (compose `restart: unless-stopped` brings it back) instead of
# silently limping along on one surface.
set -euo pipefail

# Surface 1 — FastAPI (brief mandate: /chat /ingest /sync-status /health).
uvicorn klerk.api.server:app --host 0.0.0.0 --port "${KLERK_API_PORT:-8000}" &

# Surface 2 — Studio TUI served in-browser via textual-serve.
textual serve --port "${KLERK_STUDIO_PORT:-8001}" "klerk.studio.app:main" &

# Exit (non-zero) when the first child exits; tini propagates the signal.
wait -n
