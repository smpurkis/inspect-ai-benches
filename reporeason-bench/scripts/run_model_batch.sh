#!/usr/bin/env bash
set -euo pipefail

models=(
  # "openai-api/local/SmolLM-360M-Instruct.Q6_K"
  "openai-api/local/Qwen3.5-122B-A10B-Q5_K_L-instruct"
  "openai-api/local/Qwen3.5-122B-A10B-Q5_K_L-thinking"
  "openai-api/local/Qwen3.5-35B-A3B-Q8_0-instruct"
  "openai-api/local/Qwen3.5-35B-A3B-Q8_0-thinking"
  "openai-api/local/Qwen3-Coder-Next-Q8_0"
  # "openai-api/local/LFM2-24B-A2B-Q8_0"
  "openai-api/local/Nemotron-3-Nano-30B-A3B-UD-Q8_K_XL-thinking"
  # "openai-api/local/gpt-oss-120b-Derestricted.MXFP4_MOE-low"
  # "openai-api/local/gpt-oss-120b-Derestricted.MXFP4_MOE-medium"
  # "openai-api/local/gpt-oss-120b-Derestricted.MXFP4_MOE-high"
)
base_url="http://localhost:8234/v1/"
api_key="purkis-home-blah"


for model in "${models[@]}"; do
  reasoning_history="none"
  if [[ "${model}" == *-thinking ]]; then
    reasoning_history="auto"
  fi

  uv run inspect eval src/reporeason_native.py \
    --model "${model}" \
    --env "LOCAL_BASE_URL=${base_url}" \
    --env "LOCAL_API_KEY=${api_key}" \
    --max-samples 2 \
    --max-connections 1 \
    --max-retries 3 \
    --continue-on-fail \
    --limit 50 \
    --epochs 1 \
    --reasoning-history "${reasoning_history}" \
    --log-dir logs
done

# for model in "${models[@]}"; do
#   OPENCODE_PROVIDER=local uv run inspect eval src/reporeason_opencode.py \
#     --model "${model}" \
#     --env "LOCAL_BASE_URL=${base_url}" \
#     --env "LOCAL_API_KEY=${api_key}" \
#     --max-samples 1 \
#     --max-retries 3 \
#     --continue-on-fail \
#     --limit 2 \
#     --epochs 1 \
#     --log-dir logs
# done
