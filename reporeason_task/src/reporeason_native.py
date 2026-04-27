"""Inspect AI task using native sandbox + bash tool for the reporeason benchmark."""

from __future__ import annotations

import importlib
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Literal, cast
from copy import deepcopy

import yaml
from tqdm import tqdm
from openai import OpenAI
from pydantic import BaseModel
from inspect_ai import Task, task
from inspect_ai.model import ModelOutput
from inspect_ai.model import _call_tools as _call_tools  # type: ignore
from inspect_ai.model._generate_config import GenerateConfig, ResponseSchema
from inspect_ai.model._providers.openai_compatible import OpenAICompatibleAPI
from inspect_ai.util._json import json_schema
from inspect_ai.util._sandbox.environment import SandboxEnvironmentSpec
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import solver, system_message, use_tools
from inspect_ai.util import LimitExceededError
from inspect_ai.model._chat_message import ChatMessageAssistant, ChatMessageUser
from inspect_ai.approval._policy import ApprovalPolicy
from inspect_ai.tool import ToolCall as InspectToolCall, bash
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import (
    ChatCompletionMessageToolCallParam,
    Function as OpenAIToolCallFunctionParam,
)
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from inspect_ai.util._sandbox.context import sandbox

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import llm_judge_config  # type: ignore
from src.prompts import render_task_prompt  # type: ignore
from src.parsing import normalize_target_value, parse_json_output  # type: ignore
from src.scoring import repo_reason_scorer  # type: ignore
from src.readonly_approver import RepeatedToolCallError, readonly_approver  # type: ignore


class FinalAnswerOutput(BaseModel):
    reason: str
    answer: str


def _patch_tool_call_parser() -> None:
    original = _call_tools.parse_tool_call
    openai_module: Any = importlib.import_module("inspect_ai.model._openai")

    def _parse_tool_call(
        id: str,
        function: str,
        arguments: Any,
        tools: list[Any] | None = None,
        type: Literal["function", "custom"] = "function",
    ):
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        return original(id, function, arguments, tools, type)

    _call_tools.parse_tool_call = _parse_tool_call  # type: ignore[assignment]
    if hasattr(openai_module, "parse_tool_call"):
        setattr(openai_module, "parse_tool_call", _parse_tool_call)


_patch_tool_call_parser()

DEFAULT_DATASET_PATH = str(PROJECT_ROOT / "datasets" / "consistent_dataset.yaml")
DEFAULT_REPO_DIR = "/repo"
DEFAULT_MAX_ASSISTANT_REPEATS = int(
    os.getenv(
        "REPOREASON_MAX_ASSISTANT_REPEATS",
        os.getenv("REPOREASON_MAX_ASSISTANT_MESSAGES", "5"),
    )
)
DEFAULT_MESSAGE_LIMIT = int(os.getenv("REPOREASON_NATIVE_MESSAGE_LIMIT", "300"))


def _archive_ok(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with tarfile.open(path, "r:gz") as tar:
            tar.getmembers()
    except (tarfile.TarError, OSError):
        return False
    return True


def _normalize_repeat_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _message_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _message_text(message: Any) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return text
    return _message_content_to_text(getattr(message, "content", None))


def _tool_call_param(tool_call: Any) -> ChatCompletionMessageToolCallParam | None:
    if isinstance(tool_call, InspectToolCall):
        arguments = tool_call.arguments
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        function: OpenAIToolCallFunctionParam = {
            "name": tool_call.function,
            "arguments": arguments,
        }
        return cast(
            ChatCompletionMessageToolCallParam,
            {
                "id": tool_call.id,
                "type": "function",
                "function": function,
            },
        )

    if isinstance(tool_call, dict):
        function_raw = tool_call.get("function")
        if not isinstance(function_raw, dict):
            return None
        function_dict = cast(dict[str, Any], function_raw)
        tool_id = tool_call.get("id")
        name = function_dict.get("name")
        if not isinstance(tool_id, str) or not isinstance(name, str):
            return None
        arguments_value = function_dict.get("arguments")
        if arguments_value is None:
            arguments_value = ""
        if not isinstance(arguments_value, str):
            arguments_value = json.dumps(arguments_value)
        function_param = cast(
            OpenAIToolCallFunctionParam,
            {
                "name": name,
                "arguments": arguments_value,
            },
        )
        return cast(
            ChatCompletionMessageToolCallParam,
            {
                "id": tool_id,
                "type": "function",
                "function": function_param,
            },
        )

    return None


def _openai_messages(messages: list[Any]) -> list[ChatCompletionMessageParam]:
    out: list[ChatCompletionMessageParam] = []
    for message in messages:
        role = getattr(message, "role", None)
        content = _message_text(message) or ""
        if role == "system":
            out.append(ChatCompletionSystemMessageParam(role="system", content=content))
            continue
        if role == "user":
            out.append(ChatCompletionUserMessageParam(role="user", content=content))
            continue
        if role == "assistant":
            tool_calls = getattr(message, "tool_calls", None) or []
            parsed_calls = [
                parsed
                for tool_call in tool_calls
                if (parsed := _tool_call_param(tool_call)) is not None
            ]
            if parsed_calls:
                out.append(
                    ChatCompletionAssistantMessageParam(
                        role="assistant",
                        content=content,
                        tool_calls=parsed_calls,
                    )
                )
            else:
                out.append(
                    ChatCompletionAssistantMessageParam(
                        role="assistant",
                        content=content,
                    )
                )
            continue
        if role == "tool":
            tool_call_id = getattr(message, "tool_call_id", None) or ""
            out.append(
                ChatCompletionToolMessageParam(
                    role="tool",
                    content=content,
                    tool_call_id=tool_call_id,
                )
            )
    return out


def _input_text_from_messages(messages: list[Any] | None) -> str:
    if not messages:
        return ""
    parts: list[str] = []
    for message in messages:
        role = getattr(message, "role", None)
        if role not in {"system", "user"}:
            continue
        content = _message_content_to_text(getattr(message, "content", None))
        if content:
            parts.append(content)
    return "\n".join(parts).strip()


def _limit_prompt_text() -> str:
    return (
        "You have reached the final allowed turn. Output your final answer now "
        "as a single JSON object with string fields and no extra text:\n"
        '{\n  "reason": "<your reasoning here>",\n  '
        '"answer": "<exact characters to fill <blank>>"\n}\n'
        "Schema:\n"
        '{\n  "type": "object",\n  "required": ["reason", "answer"],\n'
        '  "additionalProperties": false,\n  "properties": {\n'
        '    "reason": {"type": "string"},\n'
        '    "answer": {"type": "string"}\n  }\n}'
    )


def _apply_limit_prompt(state, limit_budget: int, prompt_text: str) -> bool:
    if not limit_budget:
        return False
    for message in state.messages:
        if (
            getattr(message, "role", None) == "user"
            and isinstance(getattr(message, "content", None), str)
            and message.content == prompt_text
        ):
            return False
    if len(state.messages) < limit_budget - 1:
        return False
    state.messages.append(ChatMessageUser(content=prompt_text))
    return True


def _has_limit_prompt(state, prompt_text: str) -> bool:
    for message in state.messages:
        if (
            getattr(message, "role", None) == "user"
            and isinstance(getattr(message, "content", None), str)
            and message.content == prompt_text
        ):
            return True
    return False


async def _final_answer_with_prompt(state, generate, input_text: str, prompt_text: str):
    if state.metadata is None:
        state.metadata = {}
    state.metadata["limit_prompt_text"] = prompt_text
    if not _has_limit_prompt(state, prompt_text):
        state.messages.append(ChatMessageUser(content=prompt_text))
    saved_tools = list(state.tools) if hasattr(state, "tools") else None
    if saved_tools is not None:
        state.tools = []
    try:
        state = await generate(state)
    except LimitExceededError:
        state.message_limit = None
        if not _has_limit_prompt(state, prompt_text):
            state.messages.append(ChatMessageUser(content=prompt_text))
        state = await generate(state)
    finally:
        if saved_tools is not None:
            state.tools = saved_tools
    output_text = _message_content_to_text(getattr(state.output, "completion", None))
    state.metadata = {
        **(state.metadata or {}),
        "io_stats": {
            "input": _text_stats(input_text),
            "output": _text_stats(output_text),
        },
        "limit_prompted": True,
    }
    return state


def append_to_message_state(state, message):
    state_copy = deepcopy(state)
    state.max_messages = None
    state.message_limit = None
    state._message_limit = None
    state.messages.append(message)
    state._message_limit = state_copy._message_limit
    state.message_limit = state_copy.message_limit
    state.max_messages = state_copy.max_messages


async def _force_final_answer_internal(state, prompt_text: str) -> None:
    if not _has_limit_prompt(state, prompt_text):
        append_to_message_state(state, ChatMessageUser(content=prompt_text))

    model_name = state.model.name
    if "/" not in model_name:
        model_name = f"local/{model_name}"
    schema = ResponseSchema(
        name="final_answer",
        json_schema=json_schema(FinalAnswerOutput),
        description="Final answer schema for reporeason native solver",
        strict=True,
    )
    config = GenerateConfig(response_schema=schema)
    base_url = os.getenv("LOCAL_BASE_URL")
    api_key = os.getenv("LOCAL_API_KEY")
    api = OpenAICompatibleAPI(
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
    )
    output: ModelOutput | Exception = ModelOutput(model=str(state.model))
    try:
        result = await api.generate(
            input=state.messages,
            tools=[],
            tool_choice="none",
            config=config,
        )
        output = result[0] if isinstance(result, tuple) else result
        if isinstance(output, Exception):
            raise output
    finally:
        await api.aclose()

    completion = _message_content_to_text(output.completion or output.message.text)
    append_to_message_state(state, ChatMessageAssistant(content=completion))
    state.output = output


def _text_stats(text: str | None) -> dict[str, int]:
    if not text:
        return {"chars": 0, "words": 0}
    return {"chars": len(text), "words": len(text.split())}


def _assistant_repeat_count(messages: list[Any] | None) -> int:
    if not messages:
        return 0
    count = 0
    last_text: str | None = None
    for message in reversed(messages):
        if getattr(message, "role", None) != "assistant":
            continue
        content = getattr(message, "content", None) or ""
        if not isinstance(content, str):
            content = str(content)
        normalized = _normalize_repeat_text(content)
        if not normalized:
            continue
        if last_text is None:
            last_text = normalized
            count = 1
            continue
        if normalized == last_text:
            count += 1
            continue
        break
    return count


def _write_archive(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_suffix(dest.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()
    try:
        with tarfile.open(temp_path, "w:gz") as tar:
            tar.add(src, arcname="repo")
        os.replace(temp_path, dest)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _clone_repo_archive(repo_url: str, commit_id: str, archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    temp_root = Path(tempfile.mkdtemp(prefix="reporeason_"))
    repo_path = temp_root / "repo"
    try:
        subprocess.run(
            ["git", "clone", "--quiet", repo_url, str(repo_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "checkout", "--quiet", commit_id],
            check=True,
            capture_output=True,
        )
        _write_archive(repo_path, archive_path)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def load_dataset(path: str | Path, *, repo_dir: str) -> MemoryDataset:
    dataset_path = Path(path)
    raw = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    entries = list(raw or [])
    cache_dir = PROJECT_ROOT / "workspace" / ".preloaded_repos"
    cache_dir.mkdir(parents=True, exist_ok=True)
    samples: list[Sample] = []
    clone_plan: dict[str, bool] = {}
    for idx, entry in enumerate(entries, 1):
        commit_id = entry["repo_commit_id"]
        sample_id = f"{idx:03d}"
        archive_name = f"{sample_id}-{commit_id[:8]}.tar.gz"
        archive_path = cache_dir / archive_name
        clone_plan[archive_name] = not _archive_ok(archive_path)
    total_to_clone = sum(1 for needed in clone_plan.values() if needed)
    progress = tqdm(
        total=total_to_clone,
        desc="Preloading repos",
        unit="repo",
        disable=total_to_clone == 0,
    )
    if total_to_clone:
        max_workers = min(4, total_to_clone)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, entry in enumerate(entries, 1):
                sample_id = f"{idx:03d}"
                repo_url = entry["repo_url"]
                commit_id = entry["repo_commit_id"]
                archive_name = f"{sample_id}-{commit_id[:8]}.tar.gz"
                archive_path = cache_dir / archive_name
                needs_clone = clone_plan.get(archive_name, True)
                if needs_clone:
                    futures.append(
                        executor.submit(
                            _clone_repo_archive,
                            repo_url,
                            commit_id,
                            archive_path,
                        )
                    )
            for future in concurrent.futures.as_completed(futures):
                future.result()
                progress.update(1)

    for idx, entry in enumerate(entries, 1):
        mask = entry["mask"]
        prompt = render_task_prompt(
            file_path=mask["file"],
            masked_statement=mask["masked_statement"],
            repo_dir=repo_dir,
            use_bash_tool=True,
        )
        target = normalize_target_value(mask["answer"])
        sample_id = f"{idx:03d}"
        repo_url = entry["repo_url"]
        commit_id = entry["repo_commit_id"]
        archive_name = f"{sample_id}-{commit_id[:8]}.tar.gz"
        archive_path = cache_dir / archive_name
        setup = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"rm -rf {repo_dir}\n"
            f"tar -xzf /preloaded_repos/{archive_name} -C /\n"
        )
        files = {f"/preloaded_repos/{archive_name}": str(archive_path)}
        samples.append(
            Sample(
                input=prompt,
                target=target,
                id=sample_id,
                metadata={
                    "repo_url": repo_url,
                    "repo_commit_id": commit_id,
                    "mask": {
                        "file": mask["file"],
                        "assertion_statement": mask["assertion_statement"],
                        "masked_statement": mask["masked_statement"],
                    },
                },
                files=files,
                setup=setup,
            )
        )
    progress.close()
    return MemoryDataset(samples)


async def mask_test_expression(file_path: str, line: str, mask_line: str) -> None:
    env = sandbox()
    script = (
        "from pathlib import Path\n"
        "path = Path(__import__('sys').argv[1])\n"
        "assertion = __import__('sys').argv[2]\n"
        "masked = __import__('sys').argv[3]\n"
        "text = path.read_text(encoding='utf-8')\n"
        "path.write_text(text.replace(assertion, masked, 1), encoding='utf-8')\n"
    )
    await env.exec(["python3", "-c", script, file_path, line, mask_line])


@solver
def native_tool_solver(repo_dir: str = DEFAULT_REPO_DIR):
    async def solve(state, generate):
        metadata = state.metadata or {}
        repo_url = metadata.get("repo_url")
        commit_id = metadata.get("repo_commit_id")
        mask = metadata.get("mask") or {}
        file_path = mask.get("file")
        assertion = mask.get("assertion_statement")
        masked = mask.get("masked_statement")
        if not repo_url or not commit_id or not file_path:
            raise ValueError("Missing repository metadata for sample")
        if assertion is None or masked is None:
            raise ValueError("Missing mask data for sample")

        state.metadata = state.metadata or {}
        state.metadata["limit_prompt_text"] = _limit_prompt_text()
        env = sandbox()
        repo_check = await env.exec(["test", "-d", repo_dir])
        if not repo_check.success:
            raise RuntimeError(f"Repository not found at {repo_dir}")
        try:
            await mask_test_expression(
                str(Path(repo_dir) / file_path), assertion, masked
            )
            max_repeats = DEFAULT_MAX_ASSISTANT_REPEATS
            input_text = _input_text_from_messages(state.messages)
            if state.metadata is None:
                state.metadata = {}
            env_limit = os.getenv("REPOREASON_NATIVE_MESSAGE_LIMIT")
            if env_limit:
                limit_budget = int(env_limit)
            else:
                limit_budget = state.message_limit or DEFAULT_MESSAGE_LIMIT
            state.metadata["limit_budget"] = limit_budget
            prompt_text = _limit_prompt_text()
            try:
                state = await generate(state)
            except LimitExceededError as e:
                await _force_final_answer_internal(state, prompt_text)
                output_text = _message_content_to_text(
                    getattr(state.output, "completion", None)
                )
                state.metadata = {
                    **(state.metadata or {}),
                    "io_stats": {
                        "input": _text_stats(input_text),
                        "output": _text_stats(output_text),
                    },
                    "limit_prompted": True,
                }
                return state
            except RepeatedToolCallError as e:
                guard = (state.store.get("loop_guard") if state.store else None) or {}
                if state.store:
                    guard = {
                        **guard,
                        "max_tool_repeats": state.store.get(
                            "loop_guard.max_tool_repeats"
                        ),
                        "repeats": state.store.get("loop_guard.repeats"),
                        "last_tool_json": state.store.get("loop_guard.last_tool_json"),
                        "tool_json_detected": state.store.get(
                            "loop_guard.tool_json_detected"
                        ),
                    }
                loop_meta = {
                    "max_tool_repeats": guard.get("max_tool_repeats"),
                    "repeats": guard.get("repeats"),
                    "triggered": True,
                }
                raw_candidate = guard.get("last_tool_json")
                if guard.get("tool_json_detected"):
                    loop_meta["tool_json_detected"] = True
                await _force_final_answer_internal(state, prompt_text)
                output_text = _message_content_to_text(
                    getattr(state.output, "completion", None)
                )
                state.metadata = {
                    **(state.metadata or {}),
                    "loop_guard": loop_meta,
                    "io_stats": {
                        "input": _text_stats(input_text),
                        "output": _text_stats(output_text),
                    },
                }
                return state
            loop_guard_meta: dict[str, Any] | None = None
            if max_repeats > 0:
                repeat_count = _assistant_repeat_count(state.messages)
                if repeat_count >= max_repeats:
                    loop_guard_meta = {
                        "max_assistant_repeats": max_repeats,
                        "repeats": repeat_count,
                        "triggered": True,
                    }
            output_text = _message_content_to_text(
                getattr(state.output, "completion", None)
            )
            state.metadata = {
                **(state.metadata or {}),
                "io_stats": {
                    "input": _text_stats(input_text),
                    "output": _text_stats(output_text),
                },
                **({"loop_guard": loop_guard_meta} if loop_guard_meta else {}),
            }
            return state
        finally:
            await env.exec(["rm", "-rf", repo_dir])

    return solve


@task
def reporeason_native(
    dataset_path: str = DEFAULT_DATASET_PATH,
    repo_dir: str = DEFAULT_REPO_DIR,
) -> Task:
    dataset = load_dataset(dataset_path, repo_dir=repo_dir)
    return Task(
        dataset=dataset,
        solver=[
            system_message(
                f"The repo is cloned under {repo_dir}. Use the {repo_dir} path when reading files."
            ),
            use_tools(bash(timeout=60)),
            native_tool_solver(repo_dir=repo_dir),
        ],
        scorer=repo_reason_scorer(),
        message_limit=DEFAULT_MESSAGE_LIMIT,
        sandbox=SandboxEnvironmentSpec(
            type="docker",
            config=str(Path(__file__).resolve().parent / "compose.native.yaml"),
        ),
        approval=[
            ApprovalPolicy(approver=readonly_approver(), tools="bash"),
        ],
    )
