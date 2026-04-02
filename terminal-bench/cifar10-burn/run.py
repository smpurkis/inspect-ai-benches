import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from inspect_ai import task
from staged_eval import create_task

@task(name="cifar10-burn")
def run(variant_names: str | list[str] | None = "default"):
    return create_task(
        challenge_dir=Path(__file__).resolve().parent,
        variant_names=variant_names,
        bash_timeout=600,
        test_timeout=3600,
    )
