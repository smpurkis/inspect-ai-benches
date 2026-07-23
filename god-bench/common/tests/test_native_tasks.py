from __future__ import annotations

from pathlib import Path
import tomllib

from harbor.models.task.task import Task

from common.budget import load_task_contract


ROOT = Path(__file__).resolve().parents[2]


def test_all_active_tasks_are_native_harbor_tasks() -> None:
    manifests = sorted(ROOT.glob("*/task.toml"))
    assert len(manifests) == 10

    for manifest in manifests:
        task_dir = manifest.parent
        task = Task(task_dir)
        contract = load_task_contract(task_dir, strict=True)
        raw = tomllib.loads(manifest.read_text(encoding="utf-8"))
        expected_artifacts = sorted(
            f"/app/files/{pattern}" for pattern in contract.editable
        )

        assert task.config.verifier.environment_mode.value == "separate"
        assert task.config.environment.network_mode.value == "no-network"
        assert sorted(raw["artifacts"]) == expected_artifacts
        assert (task_dir / "instruction.md").is_file()
        assert (task_dir / "tests" / "test.sh").is_file()
        assert (task_dir / "tests" / "docker-compose.yaml").is_file()
        assert not (task_dir / "run.py").exists()
        assert not (task_dir / "eval.yaml").exists()
        assert not (task_dir / "compose.yaml").exists()
