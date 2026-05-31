# syntax=docker/dockerfile:1.7
#
# klerk — Document Intelligence Assistant
#
# Python-only, two-stage build (v7 — no Node/TS in the image; the dual surface
# is Textual served via textual-serve, one Python substrate):
#   1. builder: uv-driven install of the `full` extra into a venv at /app/.venv
#   2. runtime: slim image with the venv copied in + BGE-M3 weights pre-baked
#
# The `full` extra (owned by pyproject's [project.optional-dependencies])
# pulls FastAPI + uvicorn + textual-serve + the local BGE-M3 embed stack, so
# the one image serves BOTH surfaces: FastAPI on :8000 and the Studio TUI over
# the browser via textual-serve on :8001.
#
# Pre-baking BGE-M3 (~1.2GB) means cold start of the container doesn't pull
# the model on first request. The Hugging Face cache lands at /app/.hf-cache
# inside the image so the runtime layer is self-contained. The bake is gated
# by ARG KLERK_EMBED_BACKEND (default `local`) — the graded compose path keeps
# it `local` so self-hosting BGE-M3 is unambiguous; build with
# `--build-arg KLERK_EMBED_BACKEND=remote` to skip the bake for a slim image
# that points at a remote OpenAI-compatible embed endpoint at runtime.

# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# uv from the official distroless image (zero apt churn).
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Build deps for any wheels that need a C toolchain. lancedb + tantivy ship
# manylinux wheels for x86_64 / aarch64, so the toolchain is a fallback only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Resolve + install deps from the lockfile WITHOUT the project source first,
# so this layer cache-busts only when pyproject / uv.lock change. The `full`
# extra includes the server (uvicorn + textual-serve) + local embed stack.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra full

# Now install the project itself.
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra full


# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Conditionally bake BGE-M3 weights. `local` (default) bakes; `remote` skips.
ARG KLERK_EMBED_BACKEND=local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.hf-cache \
    TRANSFORMERS_OFFLINE=0 \
    PATH="/app/.venv/bin:$PATH" \
    KLERK_API_HOST=0.0.0.0 \
    KLERK_API_PORT=8000 \
    KLERK_STUDIO_PORT=8001 \
    KLERK_EMBED_BACKEND=${KLERK_EMBED_BACKEND}

# Minimal runtime libs. lancedb needs libgomp; docling needs libgl/libglib
# for its layout parser; ca-certs for HTTPS to the Nemotron proxy; tini is
# PID-1 so signals + zombie reaping work for the two concurrent processes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the prepared venv + project source from the builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY pyproject.toml uv.lock README.md ./
COPY Makefile ./
COPY docker/entrypoint.sh /usr/local/bin/klerk-entrypoint
RUN chmod +x /usr/local/bin/klerk-entrypoint

# Pre-bake BGE-M3 weights so first request doesn't pull ~1.2GB from HF.
# Gated on KLERK_EMBED_BACKEND=local; `remote` builds skip the bake entirely.
# Failure in the local path is fatal — we want the image self-contained.
RUN if [ "$KLERK_EMBED_BACKEND" = "local" ]; then \
        python -c "from FlagEmbedding import BGEM3FlagModel; BGEM3FlagModel('BAAI/bge-m3', devices=['cpu'], use_fp16=False)"; \
    else \
        echo "KLERK_EMBED_BACKEND=$KLERK_EMBED_BACKEND — skipping BGE-M3 bake (remote embed at runtime)"; \
    fi

# State directories — these are bind-mountable from the host but exist with
# sane defaults so the container runs without any volume config.
RUN mkdir -p /app/.klerk /app/.lancedb /app/.diskcache /app/.phoenix /app/data

# Non-root user. /app + cache dirs are chowned so writes work without --user.
RUN groupadd -r klerk && useradd -r -g klerk -d /app klerk \
    && chown -R klerk:klerk /app
USER klerk

# 8000 FastAPI · 8001 Studio over textual-serve · 6006 Phoenix UI
EXPOSE 8000 8001 6006

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# tini reaps zombies + forwards signals to the two concurrent processes.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["klerk-entrypoint"]
