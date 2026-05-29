#!/usr/bin/env bash
# scripts/setup-local-llm.sh — STRETCH (item 26)
#
# Sets up a fully on-prem Bahasa-strong inference path for klerk's
# `--locale id` mode. Aligns with Indonesia's PDP Law 2026 local-inference
# story without requiring an NIM endpoint.
#
# This script DOES NOT run automatically. It is provided as documentation +
# tooling so the reviewer can opt in. The default `klerk ask --locale id`
# path uses Qwen3-on-NIM via the same Nemotron endpoint (see
# src/klerk/llm/router.py + .env.example).
#
# Steps (each opt-in; rerun safely):
#   1. Install llama.cpp (build from source; cmake + gcc/clang required)
#   2. Download a Bahasa-strong small model (Gemma 3 E4B-IT or Qwen 3.5 small)
#   3. Launch llama.cpp in server mode on :8080 (OpenAI-compatible)
#   4. Print the env-var snippet to point klerk's router at it
#
# Reviewer can stop after any step.

set -euo pipefail

# ─── Defaults (override via env) ─────────────────────────────────────────────
LLAMA_DIR="${KLERK_LLAMA_DIR:-$HOME/.klerk/llama.cpp}"
MODEL_DIR="${KLERK_MODEL_DIR:-$HOME/.klerk/models}"
MODEL_PRESET="${KLERK_LOCAL_MODEL:-gemma3-e4b-it}"   # gemma3-e4b-it | qwen35-7b-it
SERVE_PORT="${KLERK_LOCAL_PORT:-8080}"

# Model presets — quantized GGUF weights, one short tag per model.
# Reviewer can override with KLERK_LOCAL_MODEL_URL + KLERK_LOCAL_MODEL_NAME.
case "$MODEL_PRESET" in
  gemma3-e4b-it)
    DEFAULT_URL="https://huggingface.co/lmstudio-community/gemma-3-e4b-it-GGUF/resolve/main/gemma-3-e4b-it-Q4_K_M.gguf"
    DEFAULT_NAME="gemma-3-e4b-it-Q4_K_M.gguf"
    ;;
  qwen35-7b-it)
    DEFAULT_URL="https://huggingface.co/Qwen/Qwen3.5-7B-Instruct-GGUF/resolve/main/Qwen3.5-7B-Instruct-Q4_K_M.gguf"
    DEFAULT_NAME="Qwen3.5-7B-Instruct-Q4_K_M.gguf"
    ;;
  *)
    echo "unknown preset: $MODEL_PRESET (use gemma3-e4b-it | qwen35-7b-it, or set KLERK_LOCAL_MODEL_URL + KLERK_LOCAL_MODEL_NAME)" >&2
    exit 1
    ;;
esac

MODEL_URL="${KLERK_LOCAL_MODEL_URL:-$DEFAULT_URL}"
MODEL_NAME="${KLERK_LOCAL_MODEL_NAME:-$DEFAULT_NAME}"

# ─── 1. llama.cpp ─────────────────────────────────────────────────────────────
install_llama_cpp() {
  if [[ -x "$LLAMA_DIR/build/bin/llama-server" ]]; then
    echo "✓ llama.cpp already built at $LLAMA_DIR"
    return
  fi
  echo "→ building llama.cpp at $LLAMA_DIR ..."
  mkdir -p "$(dirname "$LLAMA_DIR")"
  if [[ ! -d "$LLAMA_DIR" ]]; then
    git clone --depth=1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
  fi
  (
    cd "$LLAMA_DIR"
    cmake -B build -DGGML_NATIVE=ON -DGGML_CCACHE=OFF >/dev/null
    cmake --build build --config Release -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
  )
  echo "✓ llama.cpp built"
}

# ─── 2. Model download ────────────────────────────────────────────────────────
download_model() {
  mkdir -p "$MODEL_DIR"
  local target="$MODEL_DIR/$MODEL_NAME"
  if [[ -s "$target" ]]; then
    echo "✓ model already present: $target"
    return
  fi
  echo "→ downloading model: $MODEL_NAME"
  echo "   from: $MODEL_URL"
  echo "   to:   $target"
  echo "   (size varies by preset; Gemma 3 E4B Q4_K_M ≈ 3.0 GB)"
  curl -L --fail -o "$target" "$MODEL_URL"
  echo "✓ model downloaded"
}

# ─── 3. Launch ────────────────────────────────────────────────────────────────
launch_server() {
  local target="$MODEL_DIR/$MODEL_NAME"
  if [[ ! -s "$target" ]]; then
    echo "✗ model file missing: $target — run with 'download' first." >&2
    exit 1
  fi
  echo "→ starting llama-server on :$SERVE_PORT (OpenAI-compatible)"
  exec "$LLAMA_DIR/build/bin/llama-server" \
    --model "$target" \
    --port "$SERVE_PORT" \
    --host 0.0.0.0 \
    -c 8192 \
    --jinja \
    --metrics
}

print_env_snippet() {
  cat <<EOF

╭─ klerk: point at local LLM ──────────────────────────────────────────────╮
│                                                                          │
│   Add to .env:                                                           │
│                                                                          │
│   KLERK_QWEN_BASE_URL=http://localhost:$SERVE_PORT/v1                        │
│   KLERK_QWEN_MODEL=$MODEL_NAME                                           │
│                                                                          │
│   Then:                                                                  │
│     uv run klerk ask "Berapa lama cuti melahirkan?" --locale id          │
│                                                                          │
│   The router (src/klerk/llm/router.py) sends --locale id calls to        │
│   KLERK_QWEN_BASE_URL via LiteLLM's OpenAI-compatible client.            │
│                                                                          │
╰──────────────────────────────────────────────────────────────────────────╯
EOF
}

# ─── Dispatch ─────────────────────────────────────────────────────────────────
case "${1:-help}" in
  install)     install_llama_cpp ;;
  download)    download_model ;;
  serve)       launch_server ;;
  env)         print_env_snippet ;;
  all)         install_llama_cpp; download_model; launch_server ;;
  help|*)
    cat <<EOF
klerk local-LLM setup — STRETCH path for the --locale id Bahasa route.

Usage: $0 <command>

Commands:
  install    Build llama.cpp from source at $LLAMA_DIR
  download   Pull the GGUF model ($MODEL_PRESET) to $MODEL_DIR
  serve      Start llama-server (OpenAI-compatible) on :$SERVE_PORT
  env        Print the .env snippet to point klerk at the local server
  all        install → download → serve (blocking)

Override defaults via:
  KLERK_LLAMA_DIR=/path/to/llama.cpp
  KLERK_MODEL_DIR=/path/to/models
  KLERK_LOCAL_MODEL=gemma3-e4b-it | qwen35-7b-it
  KLERK_LOCAL_MODEL_URL=https://...    (custom HF URL)
  KLERK_LOCAL_MODEL_NAME=custom.gguf   (filename)
  KLERK_LOCAL_PORT=8080

Documented in docs/design-decisions.md (STRETCH item #26) +
docs/bahasa-eval.md (PDP Law 2026 local-inference story).
EOF
    ;;
esac
