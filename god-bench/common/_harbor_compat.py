"""Local copy of two helpers that used to live in inspect_evals.harbor.harbor.

inspect-evals 0.10.x dropped the `harbor` submodule. These two functions are
the only pieces god-bench used; vendoring them here removes that dependency.
Source: inspect-evals 0.3.x, harbor/harbor.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml
from platformdirs import user_cache_dir

from inspect_ai.dataset import Sample
from inspect_ai.util import SandboxEnvironmentSpec


_CACHE_PATH = Path(user_cache_dir("inspect_evals"))


def _generate_local_build_compose(
    challenges_dir: Path,
    compose_cache_dir: Path,
    eval_name: str,
) -> Path:
    compose_cache_dir.mkdir(parents=True, exist_ok=True)

    challenge_dir = challenges_dir / eval_name
    environment_dir = challenge_dir / "environment"
    original_compose_path = challenge_dir / "compose.yaml"

    if not environment_dir.exists():
        raise FileNotFoundError(
            f"Cannot build image locally for {eval_name}: environment/ directory not found."
        )

    with open(original_compose_path) as f:
        config = yaml.safe_load(f)

    if "services" in config and "default" in config["services"]:
        config["services"]["default"]["build"] = {
            "context": str(environment_dir.absolute()),
            "dockerfile": "Dockerfile",
        }
        config["services"]["default"].pop("image", None)

    output_path = compose_cache_dir / f"{eval_name}-local-build.yaml"
    with open(output_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    return output_path


def _convert_sandbox_for_local_build(
    challenges_dir: Path,
) -> Callable[[Sample], list[Sample]]:
    """Convert sample sandbox configs to use local Docker builds."""
    compose_cache_dir = _CACHE_PATH / "harbor" / "compose_files"

    def mapper(sample: Sample) -> list[Sample]:
        eval_name = sample.metadata.get("eval_name") if sample.metadata else None
        if not eval_name:
            raise ValueError(f"Sample {sample.id} has no eval_name in metadata")

        new_compose_path = _generate_local_build_compose(
            challenges_dir, compose_cache_dir, eval_name
        )
        new_sandbox = SandboxEnvironmentSpec(
            type="docker", config=str(new_compose_path)
        )
        return [sample.model_copy(deep=True, update={"sandbox": new_sandbox})]

    return mapper
