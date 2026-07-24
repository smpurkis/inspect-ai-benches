"""GOD-Bench adapters for Harbor's native Pi and OpenCode agents."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
from typing import Any

from harbor.agents.installed.opencode import OpenCode
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from .budget import load_task_contract
from .budgeted_tools import ARTIFACT_FILES_ROOT


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
        try:
            await super().run(instruction, environment, context)
        finally:
            await _publish_task_files(environment)

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
