from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest
from harbor.models.task.config import NetworkMode

from common.harbor_agent import GodBenchAgent, validate_plan


class Result:
    def __init__(self, return_code=0, stdout="", stderr=""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class MemoryEnvironment:
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.directories = {"/app", "/logs", "/logs/agent", "/logs/artifacts"}
        self.commands: list[str] = []
        self.network_policy = SimpleNamespace(network_mode=NetworkMode.NO_NETWORK)

    async def empty_dirs(self, dirs, chmod=True):
        for root in dirs:
            self.files = {p: v for p, v in self.files.items() if not p.startswith(root + "/")}
            self.directories.add(root)
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
        self.commands.append(command)
        words = shlex.split(command)
        if command.startswith("chmod ") or command.startswith("mkdir ") or command.startswith("rm -rf"):
            if command.startswith("rm -rf") and "/logs/artifacts/god-bench/files" in command:
                self.files = {p: v for p, v in self.files.items() if not p.startswith("/logs/artifacts/god-bench/files/")}
            return Result()
        if words[:3] == ["realpath", "-e", "--"]:
            path = words[3]
            return Result(0, path + "\n") if path in self.files or path in self.directories else Result(1)
        if words[:2] == ["test", "-L"]:
            return Result(1)
        if words[:2] == ["test", "-f"]:
            return Result(0 if words[2] in self.files else 1)
        if command == "ps -e -o pid=":
            return Result(0, "1\n10\n")
        if words[:3] == ["stat", "-c", "%s"]:
            path = words[-1]
            return Result(0, f"{len(self.files[path])}\n") if path in self.files else Result(1)
        if words and words[0] == "find":
            root = words[1]
            return Result(0, "\n".join(sorted(p for p in self.files if p.startswith(root + "/"))) + "\n")
        if words and words[0] == "rg":
            return Result(0, "/app/files/main.py:1:value = 1\n")
        if words[:2] == ["python3", "-c"]:
            if "os.listdir" in command and "/proc" in command:
                return Result()
            path, start, end, cap = words[-4], int(words[-3]), int(words[-2]), int(words[-1])
            data = b"".join(self.files[path].splitlines(keepends=True)[start - 1:end])[:cap]
            import base64
            return Result(0, json.dumps({"data": base64.b64encode(data).decode(), "truncated": False}))
        if "pytest" in words:
            return Result(0, "1 passed in 0.01s")
        if command == "true":
            return Result()
        raise AssertionError(command)


def _challenge(tmp_path: Path) -> Path:
    files = tmp_path / "files"
    files.mkdir(parents=True)
    (files / "main.py").write_text("value = 1\n")
    (files / "tests.py").write_text("def test_ok(): pass\n")
    (files / "contract.toml").write_text(
        "[task]\npublic_test='python3 -m pytest -q /app/files/tests.py'\nbuild='true'\n"
        "[policy]\neditable=['main.py']\n"
    )
    return tmp_path


def _response(content="", tool_calls=None, prompt=10, completion=5):
    return {
        "choices": [{"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        "_hidden_params": {"response_cost": 0.01},
    }


def test_plan_requires_exact_typed_json():
    assert validate_plan('{"target_files":["main.py"],"hypothesis":"x","first_check":"read"}')
    with pytest.raises(ValueError):
        validate_plan('{"target_files":[],"hypothesis":"x","first_check":"read"}')


def test_agent_uploads_files_runs_one_tool_at_a_time_and_populates_context(tmp_path):
    responses = [
        _response('{"target_files":["main.py"],"hypothesis":"value is wrong","first_check":"read"}'),
        _response(tool_calls=[{"id": "1", "function": {"name": "strict_edit", "arguments": json.dumps({"path": "main.py", "old_text": "value = 1", "new_text": "value = 2"})}}]),
        _response("implemented"),
    ]
    requests = []

    async def completion(**kwargs):
        requests.append(kwargs)
        return responses.pop(0)

    async def exercise():
        env = MemoryEnvironment()
        context = SimpleNamespace(n_input_tokens=None, n_cache_tokens=None, n_output_tokens=None, cost_usd=None, metadata=None)
        agent = GodBenchAgent(
            logs_dir=tmp_path / "logs",
            model_name="openai/test",
            task_dir=_challenge(tmp_path / "challenge"),
            completion_fn=completion,
        )
        await agent.setup(env)
        await agent.run("Fix the value.", env, context)
        assert env.files["/app/files/main.py"] == b"value = 2\n"
        assert env.files["/logs/artifacts/god-bench/files/main.py"] == b"value = 2\n"
        artifact = json.loads(env.files["/logs/agent/agent_usage.json"])
        assert artifact["trace"]["model_tokens"] == 45
        assert artifact["trace"]["weighted_tool_cost"] == 1
        assert context.n_input_tokens == 30
        assert context.n_cache_tokens == 0
        assert context.n_output_tokens == 15
        assert context.metadata["plan_valid"] is True
        assert requests[0]["max_tokens"] == 120
        assert requests[0]["response_format"] == {"type": "json_object"}
        assert requests[0]["temperature"] == 0.0
        assert requests[1]["parallel_tool_calls"] is False
        assert all(tool["function"]["name"] != "shell" for tool in requests[1]["tools"])

    asyncio.run(exercise())


def test_agent_rejects_symlink_task_files(tmp_path):
    challenge = _challenge(tmp_path / "challenge")
    (challenge / "files" / "link.py").symlink_to(challenge / "files" / "main.py")
    agent = GodBenchAgent(logs_dir=tmp_path, model_name="x", task_dir=challenge)
    with pytest.raises(RuntimeError, match="symlink"):
        asyncio.run(agent.setup(MemoryEnvironment()))


def test_agent_infers_task_dir_from_harbor_environment(tmp_path):
    challenge = _challenge(tmp_path / "challenge")
    environment = MemoryEnvironment()
    environment.environment_dir = challenge / "environment"
    agent = GodBenchAgent(logs_dir=tmp_path, model_name="openai/test")

    asyncio.run(agent.setup(environment))

    assert agent.task_dir == challenge.resolve()
    assert environment.files["/app/files/main.py"] == b"value = 1\n"


def test_agent_marks_missing_provider_usage_invalid(tmp_path):
    async def completion(**kwargs):
        return {"choices": [{"message": {"role": "assistant", "content": "{}"}}]}

    async def exercise():
        env = MemoryEnvironment()
        context = SimpleNamespace(
            n_input_tokens=None,
            n_cache_tokens=None,
            n_output_tokens=None,
            cost_usd=None,
            metadata=None,
        )
        agent = GodBenchAgent(
            logs_dir=tmp_path / "logs",
            model_name="openai/test",
            task_dir=_challenge(tmp_path / "challenge"),
            completion_fn=completion,
        )
        await agent.run("Fix the value.", env, context)

        assert context.metadata["usage"]["provider_usage_valid"] is False
        assert "omitted token usage" in context.metadata["final_text"]

    asyncio.run(exercise())


def test_agent_retries_invalid_plan_once(tmp_path):
    responses = [
        _response("not json"),
        _response(
            '{"target_files":["main.py"],"hypothesis":"fix",'
            '"first_check":"read"}'
        ),
        _response("finished"),
    ]

    async def completion(**kwargs):
        return responses.pop(0)

    async def exercise():
        env = MemoryEnvironment()
        context = SimpleNamespace(
            n_input_tokens=None,
            n_cache_tokens=None,
            n_output_tokens=None,
            cost_usd=None,
            metadata=None,
        )
        agent = GodBenchAgent(
            logs_dir=tmp_path / "logs",
            model_name="openai/test",
            task_dir=_challenge(tmp_path / "challenge"),
            completion_fn=completion,
        )

        await agent.run("Fix the value.", env, context)

        assert context.metadata["plan_valid"] is True
        assert context.n_output_tokens == 15

    asyncio.run(exercise())
