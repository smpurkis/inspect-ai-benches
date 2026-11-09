"""GOD-Bench adapters for Harbor's native Pi and OpenCode agents."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
from time import monotonic
from typing import Any

from harbor.agents.installed.opencode import OpenCode
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from .budget import load_task_contract
from .budgeted_tools import ARTIFACT_FILES_ROOT, ARTIFACT_USAGE_FILE
from .usage import USAGE_SCHEMA_VERSION, UsageEvent, UsageTrace


async def _stage_task_files(environment: BaseEnvironment) -> None:
    task_dir = Path(environment.environment_dir).resolve().parent
    files_dir = task_dir / "files"
    if not files_dir.is_dir() or files_dir.is_symlink():
        raise RuntimeError("task directory must contain a non-symlink files directory")
    for path in files_dir.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"task files cannot contain symlinks: {path}")

    result = await environment.empty_dirs(["/app/files"], chmod=True)
    if result is not None and result.return_code != 0:
        raise RuntimeError("could not initialize /app/files")
    await environment.upload_dir(files_dir, "/app/files")
    writable = await environment.exec(
        "chmod -R a+rwX /app/files", timeout_sec=30, user="root"
    )
    if writable.return_code != 0:
        raise RuntimeError("could not make task files writable")


async def _publish_task_files(environment: BaseEnvironment) -> None:
    task_dir = Path(environment.environment_dir).resolve().parent
    contract = load_task_contract(task_dir, strict=True)
    commands = [
        f"rm -rf -- {shlex.quote(ARTIFACT_FILES_ROOT)}",
        f"mkdir -p -- {shlex.quote(ARTIFACT_FILES_ROOT)}",
    ]
    for relative in contract.editable:
        source = f"/app/files/{relative}"
        target = f"{ARTIFACT_FILES_ROOT}/{relative}"
        commands.append(
            f"if [ -f {shlex.quote(source)} ]; then "
            f"mkdir -p -- {shlex.quote(str(Path(target).parent))} && "
            f"cp -- {shlex.quote(source)} {shlex.quote(target)}; fi"
        )
    result = await environment.exec(" && ".join(commands), timeout_sec=30)
    if result.return_code != 0:
        raise RuntimeError("could not publish editable task files")


def _pi_usage_artifact(
    output_file: Path, contract: Any, elapsed_seconds: float
) -> dict[str, Any]:
    trace = UsageTrace(elapsed_seconds=elapsed_seconds)
    turns = 0
    public_test_runs = 0
    provider_usage_valid = output_file.is_file()
    seen_tools: set[str] = set()
    tool_starts: dict[str, dict[str, Any]] = {}
    if output_file.is_file():
        text = output_file.read_bytes().decode("utf-8", errors="ignore")
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            event_type = event.get("type")
            if event_type == "message_end":
                message = event.get("message") or {}
                if message.get("role") != "assistant":
                    continue
                usage = message.get("usage") or {}
                fresh = int(usage.get("input", 0) or 0)
                cached = int(usage.get("cacheRead", 0) or 0)
                output = int(usage.get("output", 0) or 0)
                if message.get("stopReason") == "error":
                    provider_usage_valid = False
                if fresh or cached or output:
                    turns += 1
                    trace.model_input_tokens += fresh + cached
                    trace.model_output_tokens += output
            if event_type == "tool_execution_start":
                call_id = str(event.get("toolCallId", ""))
                if call_id:
                    tool_starts[call_id] = event
                continue
            if event_type != "tool_execution_end":
                continue
            call_id = str(event.get("toolCallId", ""))
            if not call_id or call_id in seen_tools:
                continue
            seen_tools.add(call_id)
            start = tool_starts.get(call_id, {})
            tool = str(start.get("toolName") or event.get("toolName", "unknown"))
            args = start.get("args") or {}
            normalized = json.dumps(args, sort_keys=True, separators=(",", ":"))
            result = event.get("result") or {}
            output_text = json.dumps(result, sort_keys=True, separators=(",", ":"))
            action_class = "read" if tool == "read" else "tool"
            tool_cost = 1
            if tool == "bash":
                command = str(args.get("command", ""))
                if "pytest" in command and "tests.py" in command:
                    action_class = "public_test"
                    public_test_runs += 1
                    tool_cost = 4
                elif any(word in command for word in ("cargo build", "go test", "make ", "wat2wasm", "javac", "ghc ")):
                    action_class = "build"
                    tool_cost = 4
                else:
                    action_class = "shell"
                    tool_cost = 2
            elif tool in {"write", "edit"}:
                action_class = "edit"
                tool_cost = 3
            trace.append(
                UsageEvent(
                    turn=max(turns, 1),
                    tool=tool,
                    normalized_command=normalized,
                    action_class=action_class,
                    tool_cost=tool_cost,
                    input_chars=len(normalized),
                    output_chars=len(output_text),
                    read_bytes=len(output_text.encode()) if tool == "read" else 0,
                    elapsed_seconds=elapsed_seconds,
                )
            )

    budget = contract.budget.as_dict()
    snapshot = {
        **budget,
        "turns": turns,
        "weighted_tool_cost": trace.weighted_tool_cost,
        "public_test_runs": public_test_runs,
        "file_read_bytes": trace.file_read_bytes,
        "no_progress_retries": trace.no_progress_retries,
        "model_tokens": trace.model_tokens,
        "elapsed_seconds": elapsed_seconds,
    }
    within_budget = (
        turns <= contract.budget.max_agent_turns
        and trace.weighted_tool_cost <= contract.budget.max_weighted_tool_cost
        and public_test_runs <= contract.budget.max_public_test_runs
        and trace.file_read_bytes <= contract.budget.max_file_read_bytes
        and trace.model_tokens <= contract.budget.max_model_tokens
        and elapsed_seconds <= contract.budget.wall_clock_seconds
    )
    return {
        "schema_version": USAGE_SCHEMA_VERSION,
        "provider_usage_valid": provider_usage_valid,
        "trace": trace.as_dict(),
        "budget": budget,
        "budget_snapshot": snapshot,
        "public_test_count": public_test_runs,
        "within_budget": within_budget,
    }


async def _publish_pi_usage(
    environment: BaseEnvironment, output_file: Path, contract: Any, elapsed: float
) -> None:
    artifact = _pi_usage_artifact(output_file, contract, elapsed)
    local_file = output_file.with_name("agent_usage.json")
    local_file.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")
    await environment.ensure_dirs([str(Path(ARTIFACT_USAGE_FILE).parent)], chmod=True)
    await environment.upload_file(local_file, ARTIFACT_USAGE_FILE)


class GodBenchPi(Pi):
    """Pi with GOD-Bench file staging and local OpenAI model registration."""

    @staticmethod
    def name() -> str:
        return "god-bench-pi"

    async def setup(self, environment: BaseEnvironment) -> None:
        task_dir = Path(environment.environment_dir).resolve().parent
        self._task_timeout = int(
            load_task_contract(task_dir, strict=True).budget.wall_clock_seconds
        )
        await super().setup(environment)
        await _stage_task_files(environment)

        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Model name must be in the format provider/model_name")
        provider, model_id = self.model_name.split("/", 1)
        base_url = self._get_env("OPENAI_BASE_URL")
        if provider != "openai" or not base_url:
            return
        config: dict[str, Any] = {
            "providers": {
                provider: {
                    "baseUrl": base_url,
                    "api": "openai-completions",
                    "apiKey": "$OPENAI_API_KEY",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [
                        {
                            "id": model_id,
                            "reasoning": True,
                            "contextWindow": 200000,
                            "maxTokens": 65536,
                        }
                    ],
                }
            }
        }
        payload = shlex.quote(json.dumps(config))
        await self.exec_as_agent(
            environment,
            command=f"mkdir -p ~/.pi/agent && printf %s {payload} > ~/.pi/agent/models.json",
        )

    async def exec_as_agent(
        self,
        environment: BaseEnvironment,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        if "pi --print --mode json" in command:
            cwd = "/app/files"
            limit = getattr(self, "_task_timeout", timeout_sec or 900)
            command = (
                f"timeout --signal=TERM --kill-after=10s {limit}s "
                f"bash -lc {shlex.quote(command)}"
            )
        return await super().exec_as_agent(
            environment,
            command,
            env=env,
            cwd=cwd,
            timeout_sec=timeout_sec,
        )

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        started = monotonic()
        try:
            await super().run(instruction, environment, context)
        finally:
            await _publish_task_files(environment)
            task_dir = Path(environment.environment_dir).resolve().parent
            contract = load_task_contract(task_dir, strict=True)
            await _publish_pi_usage(
                environment,
                self.logs_dir / self._OUTPUT_FILENAME,
                contract,
                monotonic() - started,
            )

    def populate_context_post_run(self, context: AgentContext) -> None:
        output_file = self.logs_dir / self._OUTPUT_FILENAME
        if not output_file.exists():
            return
        input_tokens = 0
        output_tokens = 0
        cache_tokens = 0
        cost = 0.0
        text = output_file.read_bytes().decode("utf-8", errors="ignore")
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if event.get("type") != "message_end":
                continue
            message = event.get("message") or {}
            if message.get("role") != "assistant":
                continue
            usage = message.get("usage") or {}
            input_tokens += int(usage.get("input", 0) or 0)
            output_tokens += int(usage.get("output", 0) or 0)
            cache_tokens += int(usage.get("cacheRead", 0) or 0)
            cost += float((usage.get("cost") or {}).get("total", 0.0) or 0.0)
        context.n_input_tokens = input_tokens + cache_tokens
        context.n_output_tokens = output_tokens
        context.n_cache_tokens = cache_tokens
        context.cost_usd = cost if cost > 0 else None


class GodBenchOpenCode(OpenCode):
    """OpenCode with GOD-Bench file staging and local endpoint configuration."""

    @staticmethod
    def name() -> str:
        return "god-bench-opencode"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.model_name or "/" not in self.model_name:
            return
        _, model_id = self.model_name.split("/", 1)
        base_url = self._get_env("OPENAI_BASE_URL")
        if base_url:
            provider = "god-bench"
            self.model_name = f"{provider}/{model_id}"
            override = {
                "small_model": self.model_name,
                "provider": {
                    provider: {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "GOD-Bench local endpoint",
                        "options": {
                            "baseURL": base_url,
                            "apiKey": "{env:OPENAI_API_KEY}",
                        },
                        "models": {
                            model_id: {
                                "name": model_id,
                                "limit": {"context": 200000, "output": 65536},
                            }
                        },
                    }
                }
            }
            self._deep_merge(self._opencode_config, override)

    async def exec_as_agent(
        self,
        environment: BaseEnvironment,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        if "opencode --model=" in command:
            cwd = "/app/files"
            limit = getattr(self, "_task_timeout", timeout_sec or 900)
            command = (
                f"timeout --signal=TERM --kill-after=10s {limit}s "
                f"bash -lc {shlex.quote(command)}"
            )
        return await super().exec_as_agent(
            environment,
            command,
            env=env,
            cwd=cwd,
            timeout_sec=timeout_sec,
        )

    async def setup(self, environment: BaseEnvironment) -> None:
        task_dir = Path(environment.environment_dir).resolve().parent
        self._task_timeout = int(
            load_task_contract(task_dir, strict=True).budget.wall_clock_seconds
        )
        await super().setup(environment)
        await _stage_task_files(environment)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        try:
            await super().run(instruction, environment, context)
        finally:
            await _publish_task_files(environment)


__all__ = ["GodBenchOpenCode", "GodBenchPi"]
