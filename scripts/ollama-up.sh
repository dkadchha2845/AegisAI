#!/usr/bin/env bash
# Start the local Ollama server if it isn't already running.
#
# Ollama is only needed for offline dataset/coach generation (PRESAGE_LLM=ollama).
# Nothing at PRESAGE runtime depends on it.
set -euo pipefail

OLLAMA=/opt/homebrew/opt/ollama/bin/ollama
HOST=${OLLAMA_HOST:-http://localhost:11434}

if curl -sf --max-time 3 "$HOST/api/tags" >/dev/null 2>&1; then
  echo "ollama already running at $HOST"
else
  echo "starting ollama..."
  # Flash attention + q8 KV cache roughly halves KV memory, which is what
  # lets a 7B model hold an 8k context comfortably on a 16GB machine.
  OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
    "$OLLAMA" serve >/tmp/ollama.log 2>&1 &
  until curl -sf --max-time 2 "$HOST/api/tags" >/dev/null 2>&1; do sleep 1; done
  echo "ollama up (log: /tmp/ollama.log)"
fi

"$OLLAMA" list
