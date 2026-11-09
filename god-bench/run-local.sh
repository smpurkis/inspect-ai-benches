#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

exec uv run python run.py \
  --model "${GOD_BENCH_MODEL:-Qwen3.8-Flash-Next-Gufo-Gyro-M-Stream}" \
  --base-url "${GOD_BENCH_BASE_URL:-http://127.0.0.1:8234/v1}" \
  --api-key "${GOD_BENCH_API_KEY:-local}" \
  "$@"
