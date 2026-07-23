"""Native Harbor external agent for the strict GOD-Bench contract."""

from __future__ import annotations

import json
from math import ceil
import os
from pathlib import Path
import shlex
from typing import Any, Awaitable, Callable

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.task.config import NetworkMode

from .budget import BudgetState, load_task_contract
from .budgeted_tools import StrictToolRuntime, ToolDefinition
from .tool_policy import is_editable_path


PLAN_PROMPT = (
    "Before using tools, return only JSON with non-empty target_files (string array), "
    "hypothesis, and first_check. Use at most 120 output tokens and do not claim to "
    "have inspected files."
)
SYSTEM_PROMPT = (
    "You are a bounded coding agent. Work only through the supplied strict tools. "
    "Never request a shell or hidden tests. Preserve files outside the contract's "
    "editable scope. Make the smallest correct change and finish when ready."
)


def validate_plan(value: str) -> dict[str, Any]:
    """Validate the mandatory, compact planning handshake."""

    try:
        plan = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("plan must be one JSON object") from error
    if not isinstance(plan, dict) or set(plan) != {
        "target_files",
        "hypothesis",
        "first_check",
    }:
        raise ValueError("plan must contain exactly the required fields")
    targets = plan["target_files"]
    if not isinstance(targets, list) or not targets or not all(
        isinstance(item, str) and item.strip() for item in targets
    ):
        raise ValueError("target_files must be a non-empty string array")
    if not all(isinstance(plan[key], str) and plan[key].strip() for key in ("hypothesis", "first_check")):
        raise ValueError("hypothesis and first_check must be non-empty strings")
    return plan


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _message_dict(response: Any) -> dict[str, Any]:
    choices = _get(response, "choices", [])
    if not choices:
        raise RuntimeError("model response contained no choices")
    message = _get(choices[0], "message")
    if hasattr(message, "model_dump"):
        result = message.model_dump(exclude_none=True)
    elif isinstance(message, dict):
        result = dict(message)
    else:
        result = {
            "role": _get(message, "role", "assistant"),
            "content": _get(message, "content", ""),
            "tool_calls": _get(message, "tool_calls", None),
        }
    result.setdefault("role", "assistant")
    result.setdefault("content", "")
    calls = result.get("tool_calls")
    if calls:
        normalized = []
        for call in calls:
            if hasattr(call, "model_dump"):
                call = call.model_dump(exclude_none=True)
            function = _get(call, "function", {})
            if hasattr(function, "model_dump"):
                function = function.model_dump(exclude_none=True)
            normalized.append(
                {
                    "id": _get(call, "id", "tool-call"),
                    "type": "function",
                    "function": {
                        "name": _get(function, "name", ""),
                        "arguments": _get(function, "arguments", "{}"),
                    },
                }
            )
        result["tool_calls"] = normalized
    return result


def _fallback_input_tokens(messages: list[dict[str, Any]]) -> int:
    encoded = json.dumps(messages, separators=(",", ":"), ensure_ascii=False).encode()
    return max(1, (len(encoded) + 1) // 2 + 256)


class GodBenchAgent(BaseAgent):
    """A one-tool-at-a-time LiteLLM loop over strict Harbor-backed tools."""

    @staticmethod
    def name() -> str:
        return "god-bench-strict"

    def version(self) -> str:
        return "1.0.0-harbor-0.20"

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        *,
        task_dir: str | Path | None = None,
        challenge_dir: str | Path | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        completion_fn: Callable[..., Awaitable[Any]] | None = None,
        build_timeout: int = 900,
        test_timeout: int = 1200,
        **kwargs: Any,
    ) -> None:
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)
        configured_dir = task_dir or challenge_dir
        self.task_dir = Path(configured_dir).expanduser().resolve() if configured_dir else None
        self.api_base = (
            api_base
            or self.extra_env.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )
        self.api_key = (
            api_key
            or self.extra_env.get("OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        self._completion_fn = completion_fn
        self.build_timeout = build_timeout
        self.test_timeout = test_timeout
        self.contract = None

    def _require_task_dir(self) -> Path:
        if self.task_dir is None:
            raise RuntimeError(
                "GodBenchAgent requires task_dir=<challenge path> in agent kwargs"
            )
        files_dir = self.task_dir / "files"
        if not files_dir.is_dir() or files_dir.is_symlink():
            raise RuntimeError("task_dir must contain a non-symlink files directory")
        for path in files_dir.rglob("*"):
            if path.is_symlink():
                raise RuntimeError(f"task files cannot contain symlinks: {path}")
        return files_dir

    async def setup(self, environment: BaseEnvironment) -> None:
        if self.task_dir is None:
            self.task_dir = Path(environment.environment_dir).resolve().parent
        files_dir = self._require_task_dir()
        self.contract = load_task_contract(self.task_dir, strict=True)
        policy = getattr(environment, "network_policy", None)
        if policy is None or policy.network_mode != NetworkMode.NO_NETWORK:
            raise RuntimeError("GodBenchAgent requires a no-network task environment")
        result = await environment.empty_dirs(["/app/files"], chmod=True)
        if result is not None and result.return_code != 0:
            raise RuntimeError("could not initialize /app/files")
        await environment.upload_dir(files_dir, "/app/files")
        protected = await environment.exec("chmod -R a-w /app/files", timeout_sec=30, user="root")
        if protected.return_code != 0:
            raise RuntimeError("could not protect task files")
        for host_file in sorted(path for path in files_dir.rglob("*") if path.is_file()):
            relative = host_file.relative_to(files_dir).as_posix()
            if not is_editable_path(f"/app/files/{relative}", self.contract.editable):
                continue
            target = f"/app/files/{relative}"
            command = (
                f"chmod a+rw -- {shlex.quote(target)} && "
                f"chmod a+rwx -- {shlex.quote(str(Path(target).parent))}"
            )
            changed = await environment.exec(command, timeout_sec=10, user="root")
            if changed.return_code != 0:
                raise RuntimeError(f"could not make editable path writable: {relative}")

    async def _completion(self, **kwargs: Any) -> Any:
        if self._completion_fn is None:
            import litellm

            self._completion_fn = litellm.acompletion
        return await self._completion_fn(**kwargs)

    def _estimate_input_tokens(self, messages: list[dict[str, Any]]) -> int:
        conservative = _fallback_input_tokens(messages)
        try:
            import litellm

            return max(
                conservative,
                int(litellm.token_counter(model=self.model_name, messages=messages)) + 256,
            )
        except Exception:
            return conservative

    async def _call_model(
        self,
        runtime: StrictToolRuntime,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not runtime.budget.permits(turns=1):
            raise RuntimeError("agent turn budget exhausted")
        if not self.model_name:
            raise RuntimeError("GodBenchAgent requires a Harbor model name")
        remaining_seconds = runtime.contract.budget.wall_clock_seconds - runtime.budget.elapsed()
        if remaining_seconds <= 0:
            raise RuntimeError("agent wall-clock budget exhausted")
        estimated_input = self._estimate_input_tokens(messages)
        remaining_tokens = (
            runtime.contract.budget.max_model_tokens - runtime.budget.model_tokens
        )
        if estimated_input >= remaining_tokens:
            raise RuntimeError("agent model-token budget cannot fit another request")
        runtime.budget.apply(turns=1)
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": min(
                max_tokens,
                max(1, remaining_tokens - estimated_input),
            ),
            "timeout": max(1, ceil(remaining_seconds)),
            "temperature": 0.0,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if tools:
            kwargs.update(
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=False,
            )
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = await self._completion(**kwargs)
        except BaseException:
            runtime.provider_usage_valid = False
            await runtime.write_usage()
            raise
        usage = _get(response, "usage", {})
        raw_input = _get(usage, "prompt_tokens", _get(usage, "input_tokens", None))
        raw_output = _get(usage, "completion_tokens", _get(usage, "output_tokens", None))
        if raw_input is None or raw_output is None:
            runtime.provider_usage_valid = False
            await runtime.write_usage()
            raise RuntimeError("provider response omitted token usage")
        try:
            input_tokens = int(raw_input)
            output_tokens = int(raw_output)
        except (TypeError, ValueError, OverflowError):
            runtime.provider_usage_valid = False
            await runtime.write_usage()
            raise RuntimeError("provider returned malformed token usage") from None
        if input_tokens < 0 or output_tokens < 0 or input_tokens + output_tokens == 0:
            runtime.provider_usage_valid = False
            await runtime.write_usage()
            raise RuntimeError("provider returned invalid token usage")
        prompt_details = _get(usage, "prompt_tokens_details", {})
        cache_tokens = int(_get(prompt_details, "cached_tokens", 0) or 0)
        runtime.trace.model_input_tokens += input_tokens
        runtime.trace.model_output_tokens += output_tokens
        runtime.model_cache_tokens += cache_tokens
        runtime.budget.apply(model_tokens=input_tokens + output_tokens)
        hidden = _get(response, "_hidden_params", {})
        cost = _get(hidden, "response_cost", 0.0) or 0.0
        if isinstance(cost, (int, float)) and cost >= 0:
            runtime.provider_cost_usd += float(cost)
        await runtime.write_usage()
        return _message_dict(response)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if self.contract is None:
            await self.setup(environment)
        assert self.contract is not None
        runtime = StrictToolRuntime(
            contract=self.contract,
            budget=BudgetState(config=self.contract.budget),
            environment=environment,
            build_timeout=self.build_timeout,
            test_timeout=self.test_timeout,
        )
        runtime.trace.task_text_tokens = (len(instruction.encode()) + 3) // 4
        runtime.trace.benchmark_boilerplate_tokens = (
            len((PLAN_PROMPT + SYSTEM_PROMPT).encode()) + 3
        ) // 4
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
            {"role": "user", "content": PLAN_PROMPT},
        ]
        plan_valid = False
        final_text = ""
        try:
            plan_error = "plan was not attempted"
            for attempt in range(2):
                plan_tokens_before = runtime.trace.model_output_tokens
                plan_message = await self._call_model(
                    runtime,
                    messages,
                    max_tokens=120,
                    response_format={"type": "json_object"},
                )
                messages.append(plan_message)
                if runtime.trace.model_output_tokens - plan_tokens_before > 120:
                    plan_error = "plan exceeded 120 billed output tokens"
                else:
                    try:
                        validate_plan(_text_content(plan_message))
                        plan_valid = True
                        break
                    except ValueError as error:
                        plan_error = str(error)
                if attempt == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Invalid plan. Retry once with only the required JSON "
                                "object and no explanation."
                            ),
                        }
                    )
            if not plan_valid:
                raise ValueError(plan_error)
            messages.append({"role": "user", "content": "Plan accepted. Implement it using only the strict tools."})
            definitions = runtime.definitions()
            by_name = {definition.name: definition for definition in definitions}
            schemas = [definition.as_openai_tool() for definition in definitions]
            final_schemas = [
                definition.as_openai_tool()
                for definition in definitions
                if definition.name in {"strict_edit", "strict_build", "run_public_tests"}
            ]
            forced_finalization = False
            while not runtime.budget.exhausted():
                active_schemas = schemas
                remaining_tokens = (
                    self.contract.budget.max_model_tokens - runtime.budget.model_tokens
                )
                estimated_next_input = self._estimate_input_tokens(messages)
                if (
                    not forced_finalization
                    and remaining_tokens <= 3 * estimated_next_input
                ):
                    forced_finalization = True
                    active_schemas = final_schemas
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Token reserve reached. Broad exploration is disabled. "
                                "Make the best implementation edit now, then use the final "
                                "build or public test only if budget permits."
                            ),
                        }
                    )
                elif forced_finalization:
                    active_schemas = final_schemas
                message = await self._call_model(
                    runtime,
                    messages,
                    max_tokens=max(1, self.contract.budget.max_model_tokens - runtime.budget.model_tokens),
                    tools=active_schemas,
                )
                messages.append(message)
                calls = message.get("tool_calls") or []
                if not calls:
                    final_text = _text_content(message)
                    break
                if len(calls) != 1:
                    for call in calls:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", "tool-call"),
                                "name": call["function"].get("name", "unknown"),
                                "content": "DENIED: exactly one tool call is allowed per model turn",
                            }
                        )
                    continue
                else:
                    call = calls[0]
                    function = call["function"]
                    definition: ToolDefinition | None = by_name.get(function["name"])
                    if definition is None:
                        output = "DENIED: unknown tool"
                    else:
                        try:
                            arguments = json.loads(function.get("arguments") or "{}")
                            if not isinstance(arguments, dict):
                                raise TypeError("tool arguments must be an object")
                            output = await definition.execute(**arguments)
                        except (TypeError, ValueError, json.JSONDecodeError) as error:
                            output = f"DENIED: invalid tool arguments: {error}"[:8000]
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", "tool-call"),
                        "name": call["function"].get("name", "unknown"),
                        "content": output,
                    }
                )
                checkpoint = runtime.budget.checkpoint()
                if checkpoint is not None:
                    mode = (
                        " Finalization mode is active: edit and use at most one final test."
                        if checkpoint >= 80
                        else " Prioritize implementation over further exploration."
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Budget checkpoint: {checkpoint}% consumed.{mode}"
                            ),
                        }
                    )
        except Exception as error:
            final_text = str(error)
        finally:
            runtime.budget.freeze_elapsed()
            await runtime.publish_editables()
            await runtime.write_usage()
            context.n_input_tokens = runtime.trace.model_input_tokens
            context.n_cache_tokens = runtime.model_cache_tokens
            context.n_output_tokens = runtime.trace.model_output_tokens
            context.cost_usd = runtime.provider_cost_usd
            context.metadata = {
                "plan_valid": plan_valid,
                "final_text": final_text[:2000],
                "usage": runtime.usage_artifact(),
                "tool_output_chars": runtime.trace.tool_output_chars,
                "weighted_tool_cost": runtime.trace.weighted_tool_cost,
                "file_read_bytes": runtime.trace.file_read_bytes,
                "no_progress_retries": runtime.trace.no_progress_retries,
                "retrieval_precision": runtime.trace.retrieval_precision,
            }


def _text_content(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content)


__all__ = ["GodBenchAgent", "validate_plan"]
