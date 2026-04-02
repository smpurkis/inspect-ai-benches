"""Run only the modified tasks for debugging.

Usage:
    LOCAL_BASE_URL=... LOCAL_API_KEY=... uv run inspect eval \
        run_modified_tasks.py@modified_tasks \
        --model openai-api/local/gpt-4.1-mini \
        --epochs 1 \
        --max-connections 3
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "common"))

from inspect_ai import Task, task
from inspect_ai.solver import Solver, solver

from staged_eval import staged_scorer


BENCH = Path(__file__).resolve().parent

# Only the tasks we've recently modified/fixed
CHALLENGE_NAMES: list[str] = [
    "pokemon-sapphire-pyboy",
    "rust-python-ctypes",
    "text-pokemon-rust",
    "nim-vm-fix",
    "physics-2d",
    "samscript-bootstrap",
    "text-pokemon-fix",
]


def _load_task(challenge_name: str, variant_names) -> Task:
    run_py = BENCH / challenge_name / "run.py"
    spec = importlib.util.spec_from_file_location(challenge_name, run_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(variant_names=variant_names)


@solver
def _dispatching_solver(solver_map: dict[str, Solver]) -> Solver:
    async def solve(state, generate):
        name = state.metadata["eval_name"]
        return await solver_map[name](state, generate)
    return solve


@task(name="modified-tasks")
def modified_tasks(variant_names: str | list[str] | None = "default") -> Task:
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
    )
