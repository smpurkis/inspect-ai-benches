"""Run all god-bench tasks as separate evals (one per challenge).

Each challenge is registered as its own @task, so inspect creates
separate eval logs with isolated token tracking.

Usage:
    uv run inspect eval god-bench/run_all.py \
        --model openai-api/local/gpt-5 \
        --max-tasks 5
"""

import importlib.util
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH / "common"))

from inspect_ai import Task, task


def _load_task(run_py: Path, name: str, variant_names) -> Task:
    spec = importlib.util.spec_from_file_location(name, run_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(variant_names=variant_names)


def _make_task(run_py: Path, challenge_name: str):
    @task(name=challenge_name)
    def _run(variant_names: str | list[str] | None = "default") -> Task:
        return _load_task(run_py, challenge_name, variant_names)
    return _run


def _discover_and_register():
    # Top-level god-bench tasks
    for run_py in sorted(BENCH.glob("*/run.py")):
        name = run_py.parent.name
        if name in ("common", "archive"):
            continue
        globals()[name.replace("-", "_")] = _make_task(run_py, name)


_discover_and_register()
