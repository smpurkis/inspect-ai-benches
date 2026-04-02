#!/usr/bin/env bash
set -euo pipefail

VENV="/home/sam/projects/repos/llm-benchmark/inspect-ai-benches/.venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$VENV/bin/inspect" ]]; then
  echo "Expected inspect CLI at $VENV/bin/inspect. Is the venv set up?" >&2
  exit 1
fi

if [[ ! -d "$SCRIPT_DIR" ]]; then
  echo "Script directory not found: $SCRIPT_DIR" >&2
  exit 1
fi

: "${MODEL:?Set MODEL to the Inspect model id (e.g., openai-api/local/DeepSeek-V3-0324)}"
: "${LOCAL_BASE_URL:?Set LOCAL_BASE_URL to your OpenAI-compatible endpoint}"
: "${LOCAL_API_KEY:?Set LOCAL_API_KEY to your API key}"

cd "$SCRIPT_DIR"

"$VENV/bin/inspect" eval "closed-terminal-bench/run_all.py@run_all" \
  --model "$MODEL" \
  --env LOCAL_BASE_URL="$LOCAL_BASE_URL" \
  --env LOCAL_API_KEY="$LOCAL_API_KEY" \
  "$@"
