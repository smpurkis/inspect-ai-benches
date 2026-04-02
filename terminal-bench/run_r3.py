#!/usr/bin/env python3
"""Launch GPT-5 benchmark round 3."""
import subprocess
import sys
import os
from datetime import datetime

os.chdir("/home/sam/projects/repos/llm-benchmark/inspect-ai-benches/terminal-bench")

log = f"logs/run_gpt5_r3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
cmd = [
    "/home/sam/.local/bin/uv", "run", "inspect", "eval",
    "run_all.py@terminal-bench",
    "--model", "openai-api/local/gpt-5",
    "--epochs", "1",
    "--max-connections", "5",
    "--log-dir", "logs/",
]

print(f"Starting benchmark, log: {log}", flush=True)
with open(log, "w") as f:
    result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)

print(f"Done, exit code: {result.returncode}", flush=True)
sys.exit(result.returncode)
