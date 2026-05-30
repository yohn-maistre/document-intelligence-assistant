# syntax=docker/dockerfile:1.7
#
# klerk — Document Intelligence Assistant
#
# Two-stage build:
#   1. builder: uv-driven install into a venv at /app/.venv
#   2. runtime: slim image with the venv copied in + BGE-M3 weights pre-baked
#
# Pre-baking BGE-M3 (~1.2GB) means cold start of the container doesn't pull
# the model on first request. The Hugging Face cache lands at /app/.hf-cache
# inside the image so the runtime layer is self-contained.

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
# so this layer cache-busts only when pyproject / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Now install the project itself.
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.hf-cache \
    TRANSFORMERS_OFFLINE=0 \
    PATH="/app/.venv/bin:$PATH" \
    KLERK_API_HOST=0.0.0.0 \
    KLERK_API_PORT=8000

# Minimal runtime libs. lancedb needs libgomp; docling needs libgl/libglib
# for its layout parser; ca-certs for HTTPS to the Nemotron proxy.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the prepared venv + project source from the builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY pyproject.toml uv.lock README.md ./
COPY Makefile ./

# Pre-bake BGE-M3 weights so first request doesn't pull ~1.2GB from HF.
# Failure here is fatal — we want the image to be self-contained.
RUN python -c "from FlagEmbedding import BGEM3FlagModel; BGEM3FlagModel('BAAI/bge-m3', devices=['cpu'], use_fp16=False)"

# State directories — these are bind-mountable from the host but exist with
# sane defaults so the container runs without any volume config.
RUN mkdir -p /app/.klerk /app/.lancedb /app/.diskcache /app/.phoenix /app/data

# Non-root user. /app + cache dirs are chowned so writes work without --user.
RUN groupadd -r klerk && useradd -r -g klerk -d /app klerk \
    && chown -R klerk:klerk /app
USER klerk

EXPOSE 8000 6006

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "klerk.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
