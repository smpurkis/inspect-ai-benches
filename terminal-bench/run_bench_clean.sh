#!/usr/bin/env -S env -i HOME=/home/sam PATH=/home/sam/.local/bin:/usr/local/bin:/usr/bin:/bin bash
# Run benchmark with clean environment (no API keys in env)
set -e
cd /home/sam/projects/repos/llm-benchmark/inspect-ai-benches/terminal-bench
LOG="logs/run_gpt5_r2c_$(date +%Y%m%d_%H%M%S).log"
echo "Starting benchmark at $(date)" > "$LOG"
LOCAL_BASE_URL="https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/" \
LOCAL_API_KEY="4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk" \
uv run inspect eval run_all.py@terminal-bench \
    --model openai-api/local/gpt-5 \
    --epochs 1 --max-connections 5 --log-dir logs/ >> "$LOG" 2>&1
echo "Done at $(date)" >> "$LOG"
