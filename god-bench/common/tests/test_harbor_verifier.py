from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shlex
from types import SimpleNamespace

from harbor.models.task.config import NetworkMode

from budget import BudgetConfig
from common.harbor_verifier import GodBenchVerifier
from usage import USAGE_SCHEMA_VERSION, UsageTrace


class Result:
    def __init__(self, return_code=0, stdout="", stderr=""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class VerifierEnvironment:
    def __init__(self, *, hidden_return_code=0):
        self.files: dict[str, bytes] = {}
        self.directories = {"/app", "/logs", "/logs/artifacts", "/logs/verifier"}
        self.network_policy = SimpleNamespace(network_mode=NetworkMode.NO_NETWORK)
        self.hidden_return_code = hidden_return_code
        self.hidden_output = "SECRET hidden assertion\n1 failed in 0.01s"

    async def empty_dirs(self, dirs, chmod=True):
        for root in dirs:
            self.files = {p: v for p, v in self.files.items() if not p.startswith(root + "/")}
            self.directories.add(root)
        return Result()

    async def ensure_dirs(self, dirs, chmod=True):
        self.directories.update(dirs)
        return Result()

    async def upload_dir(self, source, target):
        source = Path(source)
        for path in source.rglob("*"):
            if path.is_file():
                destination = target + "/" + path.relative_to(source).as_posix()
                self.files[destination] = path.read_bytes()
                self._parents(destination)

    async def upload_file(self, source, target):
        self.files[target] = Path(source).read_bytes()
        self._parents(target)

    async def download_file(self, source, target):
        if source not in self.files:
            raise FileNotFoundError(source)
        Path(target).write_bytes(self.files[source])

    def _parents(self, path):
        parent = str(Path(path).parent)
        while parent != "/":
            self.directories.add(parent)
            parent = str(Path(parent).parent)

    async def exec(self, command, **kwargs):
        words = shlex.split(command)
        if words and words[0] == "find":
            root = words[1]
            if "l" in words:
                return Result(0, "")
            selected = sorted(path for path in self.files if path.startswith(root + "/"))
            return Result(0, "\n".join(selected) + ("\n" if selected else ""))
        if words[:3] == ["realpath", "-e", "--"]:
            return Result(0, words[3] + "\n") if words[3] in self.files else Result(1)
        if words[:3] == ["stat", "-c", "%s"]:
            path = words[-1]
            return Result(0, f"{len(self.files[path])}\n") if path in self.files else Result(1)
        if words[:2] == ["test", "-f"]:
            return Result(0 if words[2] in self.files else 1)
        if words and words[0] in {"mkdir", "rm"}:
            if words[0] == "rm":
                for root in ("/app/hidden", "/app/.god-bench-verifier-plugin"):
                    self.files = {p: v for p, v in self.files.items() if not p.startswith(root + "/")}
            return Result()
        if command == "true":
            return Result()
        if command == "ps -e -o pid=":
            return Result(0, "1\n10\n")
        if words[:2] == ["python3", "-c"]:
            return Result()
        if "/app/files/tests.py" in command:
            assert self.files["/app/files/tests.py"] == b"pristine public"
            assert self.files["/app/files/main.py"] == b"candidate"
            return Result(0, "1 passed in 0.01s")
        if "/app/hidden/hidden_tests.py" in command:
            assert "-p god_bench_order" in command
            assert self.files["/app/files/tests.py"] == b"pristine public"
            return Result(self.hidden_return_code, self.hidden_output if self.hidden_return_code else "1 passed in 0.01s")
        raise AssertionError(command)


def _task(tmp_path: Path):
    task_dir = tmp_path / "task"
    files = task_dir / "files"
    hidden = task_dir / "hidden"
    files.mkdir(parents=True)
    hidden.mkdir()
    (files / "main.py").write_bytes(b"pristine")
    (files / "tests.py").write_bytes(b"pristine public")
    (files / "contract.toml").write_text(
        "[task]\npublic_test='python3 -m pytest -q /app/files/tests.py'\nbuild='true'\n"
        "[policy]\neditable=['main.py']\n"
    )
    (hidden / "hidden_tests.py").write_text("SECRET = True")
    return SimpleNamespace(task_dir=task_dir)


def _usage():
    budget = BudgetConfig()
    trace = UsageTrace(model_input_tokens=20, model_output_tokens=5, elapsed_seconds=1.0)
    return {
        "schema_version": USAGE_SCHEMA_VERSION,
        "provider_usage_valid": True,
        "trace": trace.as_dict(),
        "budget": budget.as_dict(),
        "budget_snapshot": {
            **budget.as_dict(),
            "turns": 1,
            "weighted_tool_cost": 0,
            "public_test_runs": 0,
            "file_read_bytes": 0,
            "no_progress_retries": 0,
            "model_tokens": 25,
            "elapsed_seconds": 1.0,
        },
        "public_test_count": 0,
        "within_budget": True,
    }


def test_verifier_reconstructs_pristine_overlays_editable_and_returns_rewards(tmp_path):
    async def exercise():
        env = VerifierEnvironment()
        env.files["/logs/artifacts/god-bench/files/main.py"] = b"candidate"
        env.files["/logs/artifacts/god-bench/files/tests.py"] = b"tampered public"
        env.files["/logs/artifacts/god-bench/agent_usage.json"] = json.dumps(_usage()).encode()
        paths = SimpleNamespace(verifier_dir=tmp_path / "trial" / "verifier")
        verifier = GodBenchVerifier(task=_task(tmp_path), trial_paths=paths, environment=env)
        result = await verifier.verify()
        assert result.rewards["reward"] == 1
        assert result.rewards["correctness"] == 1
        assert result.rewards["efficiency"] == 1.0
        assert result.rewards["within_budget"] == 1
        assert result.rewards["usage_valid"] == 1
        assert env.files["/app/files/tests.py"] == b"pristine public"
        metadata = json.loads((paths.verifier_dir / "god_bench_metadata.json").read_text())
        assert metadata["overlaid_files"] == ["main.py"]
        assert metadata["functional_pass"] is True
        assert isinstance(metadata["hidden_order_seed"], int)

    asyncio.run(exercise())


def test_hidden_failure_is_binary_and_hidden_output_is_redacted(tmp_path):
    async def exercise():
        env = VerifierEnvironment(hidden_return_code=1)
        env.files["/logs/artifacts/god-bench/files/main.py"] = b"candidate"
        paths = SimpleNamespace(verifier_dir=tmp_path / "trial" / "verifier")
        verifier = GodBenchVerifier(task=_task(tmp_path), trial_paths=paths, environment=env)
        result = await verifier.verify()
        encoded = (paths.verifier_dir / "god_bench_metadata.json").read_text()
        assert result.rewards["reward"] == 0
        assert result.rewards["efficiency"] == 0.0
        assert "SECRET" not in encoded
        assert "hidden assertion" not in encoded

    asyncio.run(exercise())


def test_verifier_rejects_usage_limits_that_differ_from_contract(tmp_path):
    async def exercise():
        env = VerifierEnvironment()
        env.files["/logs/artifacts/god-bench/files/main.py"] = b"candidate"
        usage = _usage()
        usage["budget"]["max_agent_turns"] += 1
        usage["budget_snapshot"]["max_agent_turns"] += 1
        env.files["/logs/artifacts/god-bench/agent_usage.json"] = json.dumps(usage).encode()
        paths = SimpleNamespace(verifier_dir=tmp_path / "trial" / "verifier")
        verifier = GodBenchVerifier(
            task=_task(tmp_path), trial_paths=paths, environment=env
        )

        result = await verifier.verify()

        assert result.rewards["correctness"] == 1
        assert result.rewards["usage_valid"] == 0
        assert result.rewards["efficiency"] == 0.0

    asyncio.run(exercise())


def test_verifier_fails_closed_when_environment_is_not_offline(tmp_path):
    async def exercise():
        env = VerifierEnvironment()
        env.network_policy.network_mode = NetworkMode.PUBLIC
        paths = SimpleNamespace(verifier_dir=tmp_path / "trial" / "verifier")
        verifier = GodBenchVerifier(task=_task(tmp_path), trial_paths=paths, environment=env)
        result = await verifier.verify()
        assert result.rewards["reward"] == 0

    asyncio.run(exercise())
