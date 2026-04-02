"""Run the distributed-log-reconstruction-stepwise task.

Usage:
    uv run inspect eval closed-terminal-bench/distributed-log-reconstruction-stepwise/run.py@run \
        --model openai-api/local/gpt-5 \
        --env LOCAL_BASE_URL="..." \
        --env LOCAL_API_KEY="..."
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))

from inspect_ai import task

from staged_eval import create_task


@task(name="distributed-log-reconstruction-stepwise")
def run(variant_names: str | list[str] | None = "default"):
    return create_task(
        challenge_dir=Path(__file__).resolve().parent,
        variant_names=variant_names,
        bash_timeout=600,
        test_timeout=1200,
        writable_patterns=["merge_shards.py"],
    )
