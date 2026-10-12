#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$PROJECT_DIR/.models/ollama"
export OLLAMA_NO_CLOUD=1
export OLLAMA_NOHISTORY=1
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_CONTEXT_LENGTH=4096
exec "${SPEAKWELL_OLLAMA:-ollama}" "$@"
