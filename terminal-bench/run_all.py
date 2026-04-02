"""Run all terminal-bench single-step tasks in one eval file.

All 22 challenges are samples within one @task, producing one .eval log.
Datasets and solvers are loaded directly from each challenge's run.py.

Usage:
    uv run inspect eval terminal-bench/run_all.py@all_tasks \
        --model openai-api/local/gpt-4.1-mini \
        --env LOCAL_BASE_URL="https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/" \
        --env LOCAL_API_KEY="..." \
        --epochs 1 \
        --max-connections 5
"""

import importlib.util
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "common"))

from inspect_ai import Task, task
from inspect_ai.scorer import Score, ScoreReducer, score_reducer, value_to_float
from inspect_ai.scorer import mean_score, max_score
from inspect_ai.solver import Solver, solver

from staged_eval import staged_scorer


@score_reducer(name="middle_3")
def middle_3_score() -> ScoreReducer:
    """Mean of the middle 3 scores — drop the best and worst epoch."""
    vtf = value_to_float()

    def reduce(scores: list[Score]) -> Score:
        sorted_vals = sorted(vtf(s.value) for s in scores)
        middle = sorted_vals[1:-1] if len(sorted_vals) >= 3 else sorted_vals
        return Score(value=statistics.mean(middle))

    return reduce


BENCH = Path(__file__).resolve().parent

CHALLENGE_NAMES: list[str] = [
    "cifar10-burn",
    "cifar10-pytorch",
    "distributed-log-reconstruction",
    "ext4-recovery",
    "git-hooks",
    "git-leak-complex",
    "nim-vm-fix",
    "nim-vm-go",
    "pandas-to-polars-single",
    "physics-2d",
    "physics-fix",
    "pokemon-battle-fix",
    "pokemon-sapphire-pyboy",
    "rust-python-ctypes",
    "rust-python-pyo3",
    "samscript-bootstrap",
    "samscript-wasi",
    "sql-migration-rebuild",
    "text-pokemon-fix",
    "text-pokemon-rust",
    "wasm-compression-wat",
    "wasm-lz77",
]


def _load_task(challenge_name: str, variant_names) -> Task:
    """Dynamically load a challenge's run.py and return its Task object."""
    run_py = BENCH / challenge_name / "run.py"
    spec = importlib.util.spec_from_file_location(challenge_name, run_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(variant_names=variant_names)


@solver
def _dispatching_solver(solver_map: dict[str, Solver]) -> Solver:
    """Routes each sample to the solver from its challenge's run.py."""

    async def solve(state, generate):
        name = state.metadata["eval_name"]
        return await solver_map[name](state, generate)

    return solve


@task(name="terminal-bench")
def all_tasks(variant_names: str | list[str] | None = "default") -> Task:
    """All 22 single-step challenges as samples in one eval."""
    all_samples = []
    solver_map: dict[str, Solver] = {}

    for name in CHALLENGE_NAMES:
        t = _load_task(name, variant_names)
        all_samples.extend(list(t.dataset))
        solver_map[name] = t.solver

    return Task(
        dataset=all_samples,
        solver=_dispatching_solver(solver_map),
        scorer=staged_scorer(),
        epochs_reducer=[mean_score(), max_score(), middle_3_score()],
    )
