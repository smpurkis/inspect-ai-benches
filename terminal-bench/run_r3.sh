#!/bin/bash
# Run GPT-5 benchmark round 3
export HOME=/home/sam
export PATH=/home/sam/.local/bin:/usr/local/bin:/usr/bin:/bin
cd /home/sam/projects/repos/llm-benchmark/inspect-ai-benches/terminal-bench
LOG="logs/run_gpt5_r3_$(date +%Y%m%d_%H%M%S).log"
echo "Starting at $(date)" >> "$LOG"
uv run inspect eval run_all.py@terminal-bench \
    --model openai-api/local/gpt-5 \
    --epochs 1 --max-connections 5 \
    --log-dir logs/ >> "$LOG" 2>&1
echo "Finished at $(date) exit=$?" >> "$LOG"
# Remove this crontab entry when done
crontab -l | grep -v run_r3.sh | crontab -
