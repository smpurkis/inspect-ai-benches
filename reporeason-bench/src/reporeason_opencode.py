"""Inspect AI task using OpenCode agent for the reporeason benchmark.

This solver launches an OpenCode instance, sends the task prompt, and streams
events in real time so that the Inspect AI TUI and web UI show tool calls and
assistant messages as they happen — not only at the end.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

import requests
import yaml
from tqdm import tqdm

from inspect_ai import Task, task
from inspect_ai.log import transcript
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.model._model import record_and_check_model_usage
from inspect_ai.model._generate_config import GenerateConfig
from inspect_ai.model._model_call import ModelCall
from inspect_ai.model._model_output import ModelUsage
from inspect_ai.model._chat_message import (
    ChatMessageAssistant,
    ChatMessageTool,
    ChatMessageUser,
)
from inspect_ai.solver import solver
from inspect_ai.tool import ToolCall
from inspect_ai.event._model import ModelEvent
from inspect_ai.event._tool import ToolEvent
from inspect_ai.approval._policy import ApprovalPolicy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import OPENCODE_CONFIG_PATH, ensure_runs_root  # type: ignore
from src.prompts import render_task_prompt  # type: ignore
from src.parsing import (  # type: ignore
    extract_final_json_object,
    looks_like_streaming_json,
    normalize_target_value,
    parse_json_output,
    _iter_json_substrings,
    _try_load_json,
    _recover_json_fields,
)
from src.scoring import repo_reason_scorer  # type: ignore
from src.readonly_approver import readonly_approver  # type: ignore
from src.opencode_client import OpenCodeClient, WorkerContext  # type: ignore

DEFAULT_DATASET_PATH = str(PROJECT_ROOT / "datasets" / "consistent_dataset.yaml")
DEFAULT_REPO_DIR = "repo"
DEFAULT_PORT_BASE = int(os.getenv("OPENCODE_PORT_BASE", "5500"))
DEFAULT_PORT_RANGE = int(os.getenv("OPENCODE_PORT_RANGE", "100"))
DEFAULT_MAX_ASSISTANT_REPEATS = int(
    os.getenv(
        "REPOREASON_MAX_ASSISTANT_REPEATS",
        os.getenv("REPOREASON_MAX_ASSISTANT_MESSAGES", "5"),
    )
)
_PORT_MUTEX = threading.Lock()
_LEASED_PORTS: set[int] = set()


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def _build_sample_id(index: int, repo_url: str, commit_id: str) -> str:
    slug = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if slug.endswith(".git"):
        slug = slug[:-4]
    return f"{index:03d}-{slug}-{commit_id[:8]}"


def load_dataset(path: str | Path, *, repo_dir: str) -> MemoryDataset:
    dataset_path = Path(path)
    raw = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    entries = list(raw or [])
    samples: list[Sample] = []
    progress = tqdm(
        total=len(entries),
        desc="Preparing samples",
        unit="sample",
        disable=len(entries) == 0,
    )
    for idx, entry in enumerate(entries, 1):
        mask = entry["mask"]
        prompt = render_task_prompt(
            file_path=mask["file"],
            masked_statement=mask["masked_statement"],
            repo_dir=f"./{repo_dir}",
        )
        target = normalize_target_value(mask["answer"])
        sample_id = _build_sample_id(idx, entry["repo_url"], entry["repo_commit_id"])
        samples.append(
            Sample(
                input=prompt,
                target=target,
                id=sample_id,
                metadata={
                    "repo_url": entry["repo_url"],
                    "repo_commit_id": entry["repo_commit_id"],
                    "mask": {
                        "file": mask["file"],
                        "assertion_statement": mask["assertion_statement"],
                        "masked_statement": mask["masked_statement"],
                    },
                },
            )
        )
        progress.update(1)
    progress.close()
    return MemoryDataset(samples)


# ---------------------------------------------------------------------------
# Port management
# ---------------------------------------------------------------------------


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        sock.listen(1)
        return sock.getsockname()[1]


class _PortLease:
    def __init__(self, port: int, handle, lock_path: Path) -> None:
        self.port = port
        self._handle = handle
        self._lock_path = lock_path

    def release(self) -> None:
        try:
            if self._handle:
                self._handle.close()
        finally:
            self._handle = None
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                return
            if (
                self.port >= DEFAULT_PORT_BASE
                and self.port < DEFAULT_PORT_BASE + DEFAULT_PORT_RANGE
            ):
                with _PORT_MUTEX:
                    _LEASED_PORTS.discard(self.port)


def _ports_root() -> Path:
    root = ensure_runs_root() / "opencode_ports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _acquire_port_lease() -> _PortLease:
    ports_root = _ports_root()
    for port in range(DEFAULT_PORT_BASE, DEFAULT_PORT_BASE + DEFAULT_PORT_RANGE):
        with _PORT_MUTEX:
            if port in _LEASED_PORTS:
                continue
            _LEASED_PORTS.add(port)
        lock_path = ports_root / f"port-{port}.lock"
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            with _PORT_MUTEX:
                _LEASED_PORTS.discard(port)
            continue
        if not _port_is_available(port):
            handle.close()
            with _PORT_MUTEX:
                _LEASED_PORTS.discard(port)
            continue
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        return _PortLease(port, handle, lock_path)
    return _PortLease(_pick_free_port(), None, ports_root / "port-ephemeral.lock")


# ---------------------------------------------------------------------------
# Repo setup
# ---------------------------------------------------------------------------


def setup_repo(repo_url: str, commit_id: str, dest_path: Path) -> Path:
    if dest_path.exists():
        shutil.rmtree(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--quiet", repo_url, str(dest_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest_path), "checkout", "--quiet", commit_id],
        check=True,
        capture_output=True,
    )
    return dest_path


def mask_test_expression(file_path: str, line: str, mask_line: str) -> None:
    content = Path(file_path).read_text(encoding="utf-8")
    masked_content = content.replace(line, mask_line, 1)
    Path(file_path).write_text(masked_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Message / text extraction helpers
# ---------------------------------------------------------------------------


def _message_parts(message: dict[str, Any]) -> list[dict[str, Any]]:
    parts = message.get("parts")
    if isinstance(parts, list):
        return parts
    content = message.get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    text = message.get("text")
    if isinstance(text, str):
        return [{"type": "text", "text": text}]
    nested = message.get("message")
    if isinstance(nested, dict):
        return _message_parts(nested)
    return []


def _extract_text_from_part(part: dict[str, Any]) -> str | None:
    for key in ("text", "content", "value", "data", "delta", "output"):
        val = part.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    nested = _extract_text_from_part(item)
                    if nested:
                        return nested
        if isinstance(val, dict):
            nested = _extract_text_from_part(val)
            if nested:
                return nested
    return None


def _extract_text_from_message(message: dict[str, Any]) -> str | None:
    for key in ("content", "text", "data"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            nested = _extract_text_from_message(val)
            if nested:
                return nested
    parts_text: list[str] = []
    for part in _message_parts(message):
        if part.get("type") == "tool":
            continue
        t = _extract_text_from_part(part)
        if t:
            parts_text.append(t)
    if parts_text:
        return "".join(parts_text).strip()
    return None


def _extract_last_assistant_text(
    messages_payload: list[dict[str, Any]] | None,
) -> str | None:
    if not messages_payload:
        return None
    for message in reversed(messages_payload):
        info = message.get("info") or {}
        role = info.get("role") or message.get("role")
        if role != "assistant":
            continue
        text = _extract_text_from_message(message)
        if text:
            return text
        for part in reversed(_message_parts(message)):
            if part.get("type") != "tool":
                text = (_extract_text_from_part(part) or "").strip()
                if text:
                    return text
    return None


def _stringify_tool_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, indent=2)
    except TypeError:
        return str(output)


# ---------------------------------------------------------------------------
# Text sanitisation
# ---------------------------------------------------------------------------


def _sanitize_assistant_text(text: str) -> str:
    if not text:
        return ""
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered == "json":
            continue
        if "tool_call" in lowered:
            continue
        if "tool" in lowered and "call" in lowered:
            continue
        if "tool" in lowered and "begin" in lowered:
            continue
        if "tool" in lowered and "sep" in lowered:
            continue
        if "tool" in lowered and "function" in lowered:
            continue
        if "tool" in lowered and "json" in lowered and len(stripped) <= 12:
            continue
        cleaned_lines.append(line)
    cleaned_text = "\n".join(cleaned_lines).strip()
    parsed = extract_final_json_object(cleaned_text)
    if parsed:
        return "json\n" + json.dumps(parsed, indent=2, ensure_ascii=True)
    if looks_like_streaming_json(cleaned_text):
        return ""
    return cleaned_text


def _input_text_from_opencode_messages(
    messages_payload: list[dict[str, Any]] | None,
) -> str:
    if not messages_payload:
        return ""
    parts: list[str] = []
    for message in messages_payload:
        info = message.get("info") or {}
        role = info.get("role") or message.get("role")
        if role not in {"system", "user"}:
            continue
        text = _extract_text_from_message(message) or ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _text_stats(text: str | None) -> dict[str, int]:
    if not text:
        return {"chars": 0, "words": 0}
    return {"chars": len(text), "words": len(text.split())}


def _start_model_event(
    transcript_obj,
    *,
    model: str,
    prompt: str,
    request: dict[str, Any] | None = None,
) -> tuple[ModelEvent, ModelCall]:
    call_payload = request or {}
    call_payload.setdefault("prompt", prompt)
    model_call = ModelCall.create(call_payload, None)
    event = ModelEvent(
        model=model,
        role=None,
        input=[ChatMessageUser(content=prompt, source="generate")],
        tools=[],
        tool_choice="auto",
        config=GenerateConfig(),
        output=ModelOutput.from_content(model, ""),
        cache=None,
        call=model_call,
        pending=True,
    )
    transcript_obj._event(event)
    return event, model_call


def _update_model_event(
    transcript_obj,
    *,
    event: ModelEvent,
    model: str,
    text: str | None,
) -> None:
    if not text:
        return
    event.output = ModelOutput.from_content(model, text)
    event.pending = True
    transcript_obj._event_updated(event)


def _finalize_model_event(
    transcript_obj,
    *,
    event: ModelEvent,
    call: ModelCall,
    model: str,
    completion: str | None,
    response: dict[str, Any],
) -> None:
    event.output = ModelOutput.from_content(model, completion or "")
    event.pending = None
    call.set_response(response)
    event.call = call
    transcript_obj._event_updated(event)


def _emit_tool_events(
    transcript_obj,
    messages_payload: list[dict[str, Any]] | None,
    tool_events: dict[str, ToolEvent],
) -> None:
    if not messages_payload:
        return
    for msg_index, message in enumerate(messages_payload):
        for part_index, part in enumerate(_message_parts(message)):
            if part.get("type") != "tool":
                continue
            tool_name = part.get("tool") or "tool"
            state = part.get("state") or {}
            tool_input = state.get("input") or {}
            tool_output = state.get("output")
            tool_call_id = f"tool_{msg_index}_{part_index}"
            tool_args = (
                tool_input if isinstance(tool_input, dict) else {"input": tool_input}
            )
            event = tool_events.get(tool_call_id)
            if event is None:
                event = ToolEvent(
                    id=tool_call_id,
                    function=tool_name,
                    arguments=tool_args,
                    result="",
                    pending=True if tool_output is None else None,
                )
                tool_events[tool_call_id] = event
                transcript_obj._event(event)
            if tool_output is not None:
                result_text = _stringify_tool_output(tool_output)
                if event.pending:
                    event._set_result(
                        result=result_text,
                        truncated=None,
                        error=None,
                        waiting_time=0.0,
                        agent=None,
                        failed=None,
                        message_id=None,
                    )
                    transcript_obj._event_updated(event)
                elif result_text != event.result:
                    event.result = result_text
                    transcript_obj._event_updated(event)


def _assistant_content_from_parts(parts: list[dict[str, Any]]) -> str:
    raw_parts: list[str] = []
    for part in parts:
        if part.get("type") == "tool":
            continue
        text = _extract_text_from_part(part)
        if text:
            raw_parts.append(text)
    if not raw_parts:
        return ""
    return _sanitize_assistant_text("".join(raw_parts))


def _drop_tool_call_artifacts(content: str) -> bool:
    if not content:
        return True
    stripped = content.strip()
    lowered = stripped.lower()
    if lowered.startswith("json") and len(stripped) < 200:
        return True
    if "filePath" in stripped or "pattern" in stripped:
        return True
    if stripped.count("json") >= 3 and stripped.count("{") >= 2:
        return True
    # When a message has tool calls AND a JSON answer, the answer is
    # premature — the model will refine it after the tool results.
    parsed = parse_json_output(stripped)
    if parsed and isinstance(parsed, dict) and "answer" in parsed:
        return True
    return False


# ---------------------------------------------------------------------------
# Tool-call extraction from OpenCode message parts
# ---------------------------------------------------------------------------


def _tool_calls_from_parts(
    parts: list[dict[str, Any]],
    *,
    msg_index: int = 0,
) -> tuple[list[ToolCall], list[ChatMessageTool]]:
    """Extract tool calls and tool result messages from OpenCode parts."""
    tool_calls: list[ToolCall] = []
    tool_messages: list[ChatMessageTool] = []
    for part_index, part in enumerate(parts):
        if part.get("type") != "tool":
            continue
        tool_name = part.get("tool") or "tool"
        state = part.get("state") or {}
        tool_input = state.get("input") or {}
        tool_output = state.get("output")
        tool_call_id = f"tool_{msg_index}_{part_index}"
        tool_calls.append(
            ToolCall(
                id=tool_call_id,
                function=tool_name,
                arguments=tool_input
                if isinstance(tool_input, dict)
                else {"input": tool_input},
            )
        )
        if tool_output is not None:
            tool_messages.append(
                ChatMessageTool(
                    content=_stringify_tool_output(tool_output),
                    source="generate",
                    tool_call_id=tool_call_id,
                    function=tool_name,
                )
            )
    return tool_calls, tool_messages


# ---------------------------------------------------------------------------
# Event emission helpers
# ---------------------------------------------------------------------------


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    return 0


def _extract_usage_from_messages(
    messages_payload: list[dict[str, Any]] | None,
) -> ModelUsage | None:
    if not messages_payload:
        return None
    usage: ModelUsage | None = None
    for message in messages_payload:
        info = message.get("info") or {}
        if info.get("role") != "assistant":
            continue
        tokens = info.get("tokens")
        if not isinstance(tokens, dict):
            continue
        cache = tokens.get("cache")
        cache_read = None
        cache_write = None
        if isinstance(cache, dict):
            if cache.get("read") is not None:
                cache_read = _coerce_int(cache.get("read"))
            if cache.get("write") is not None:
                cache_write = _coerce_int(cache.get("write"))
        input_tokens = _coerce_int(tokens.get("input"))
        output_tokens = _coerce_int(tokens.get("output"))
        current = ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens_cache_read=cache_read,
            input_tokens_cache_write=cache_write,
            reasoning_tokens=(
                _coerce_int(tokens.get("reasoning"))
                if tokens.get("reasoning") is not None
                else None
            ),
        )
        usage = current if usage is None else usage + current
    return usage


# ---------------------------------------------------------------------------
# OpenCode-to-chat conversion
# ---------------------------------------------------------------------------


def _opencode_messages_to_chat(
    messages_payload: list[dict[str, Any]] | None,
    *,
    model: str,
    include_user: bool = False,
) -> list[Any]:
    if not messages_payload:
        return []
    chat_messages: list[Any] = []
    for msg_index, message in enumerate(messages_payload):
        info = message.get("info") or {}
        role = info.get("role") or message.get("role") or "assistant"
        parts = _message_parts(message)
        tool_calls, tool_msgs = _tool_calls_from_parts(parts, msg_index=msg_index)
        content = _assistant_content_from_parts(parts)
        if role == "user":
            if include_user and content:
                chat_messages.append(
                    ChatMessageUser(content=content, source="generate")
                )
        else:
            if tool_calls and _drop_tool_call_artifacts(content):
                content = ""
            chat_messages.append(
                ChatMessageAssistant(
                    content=content,
                    source="generate",
                    model=model,
                    tool_calls=tool_calls or None,
                )
            )
        chat_messages.extend(tool_msgs)
    return chat_messages


def _has_assistant_output(messages_payload: list[dict[str, Any]] | None) -> bool:
    if not messages_payload:
        return False
    for message in messages_payload:
        info = message.get("info") or {}
        role = info.get("role") or message.get("role")
        if role != "assistant":
            continue
        if _extract_text_from_message(message):
            return True
        for part in _message_parts(message):
            if part.get("type") == "tool":
                return True
            text = _extract_text_from_part(part) or ""
            if text.strip():
                return True
    return False


def _normalize_repeat_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _assistant_repeat_count(messages_payload: list[dict[str, Any]] | None) -> int:
    if not messages_payload:
        return 0
    count = 0
    last_text: str | None = None
    for message in reversed(messages_payload):
        info = message.get("info") or {}
        role = info.get("role") or message.get("role")
        if role != "assistant":
            continue
        text = _extract_text_from_message(message) or ""
        normalized = _normalize_repeat_text(text)
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


# ---------------------------------------------------------------------------
# Polling / waiting
# ---------------------------------------------------------------------------


def _wait_for_assistant_messages(
    client: OpenCodeClient,
    session_id: str,
    *,
    timeout: float = 180.0,
    poll_interval: float = 1.5,
    require_json: bool = False,
    max_assistant_repeats: int | None = None,
    on_poll: Callable[[], None] | None = None,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_messages: list[dict[str, Any]] | None = None
    while time.monotonic() < deadline:
        if on_poll:
            on_poll()
        messages = client.fetch_messages(session_id)
        last_messages = messages
        if max_assistant_repeats is not None:
            if _assistant_repeat_count(messages) >= max_assistant_repeats:
                return messages
        if require_json:
            text = _extract_last_assistant_text(messages)
            if text:
                if parse_json_output(text):
                    return messages
                if looks_like_streaming_json(text):
                    time.sleep(poll_interval)
                    continue
                if text.strip().startswith("{"):
                    time.sleep(poll_interval)
                    continue
                return messages
        else:
            if _has_assistant_output(messages):
                return messages
        time.sleep(poll_interval)
    logger.warning(
        "Polling timed out after %.0fs for session %s – %d messages fetched, "
        "no assistant output detected",
        timeout,
        session_id,
        len(last_messages or []),
    )
    return last_messages or []


# ---------------------------------------------------------------------------
# OpenCode message sending / model resolution
# ---------------------------------------------------------------------------


def _resolve_opencode_model(model: str) -> tuple[str | None, str | None]:
    override = os.getenv("OPENCODE_MODEL")
    if override:
        if "/" in override:
            provider, model_id = override.split("/", 1)
            return provider, model_id
        return None, None
    if not model or "/" not in model:
        return None, None
    provider, model_id = model.split("/", 1)
    if provider == "openai-api" and model_id.startswith("local/"):
        bare_model = model_id.split("/", 1)[-1]
        # LOCAL_BASE_URL is the authoritative source — it tells us which
        # Azure endpoint the eval is actually pointed at.
        base_url = os.getenv("LOCAL_BASE_URL", "")
        if ".services.ai.azure.com" in base_url:
            return "openai-custom-endpoint", bare_model
        if (
            ".cognitiveservices.azure.com" in base_url
            or ".openai.azure.com" in base_url
        ):
            return "openai-custom-endpoint", bare_model
        # Fall back to OPENCODE_PROVIDER only when URL detection is not possible.
        explicit = os.getenv("OPENCODE_PROVIDER")
        if explicit:
            return explicit, bare_model
        return "openai-custom-endpoint", bare_model
    return provider, model_id


def _send_opencode_message(
    ctx: WorkerContext,
    session_id: str,
    prompt: str,
    *,
    model: str,
    agent: str | None = None,
) -> dict[str, Any]:
    provider_id, model_id = _resolve_opencode_model(model)
    logger.info(
        "Sending message to OpenCode session=%s provider=%s model=%s",
        session_id,
        provider_id,
        model_id,
    )
    payload: dict[str, Any] = {
        "parts": [{"type": "text", "text": prompt}],
    }
    if provider_id and model_id:
        payload["model"] = {"providerID": provider_id, "modelID": model_id}
    if agent:
        payload["agent"] = agent
    resp = requests.post(
        f"{ctx.base_url}/session/{session_id}/message",
        json=payload,
        timeout=3600,
    )
    resp.raise_for_status()
    if not resp.content:
        logger.warning("OpenCode returned empty response for session %s", session_id)
        return {}
    try:
        return resp.json()
    except requests.JSONDecodeError:
        logger.warning("OpenCode returned non-JSON response for session %s", session_id)
        return {}


def _build_final_prompt(prompt: str) -> str:
    return (
        "Now provide your FINAL answer only as the JSON object described "
        "above.  Output ONLY the JSON — no explanation, no markdown fences."
    )


def _rewrite_prompt_repo_path(prompt: str, repo_dir: str) -> str:
    return prompt.replace("./repo", repo_dir).replace("./{repo_dir}", repo_dir)


def _effective_repo_dir(repo_dir: str) -> str:
    if repo_dir in {"repo", "./repo"}:
        return "."
    return repo_dir


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


@solver
def opencode_solver(repo_dir: str = DEFAULT_REPO_DIR):
    def _solve_sync(state, transcript_obj):
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

        repo_root = ensure_runs_root() / f"repo_{uuid.uuid4().hex[:8]}"
        setup_repo(repo_url, commit_id, repo_root)
        mask_test_expression(str(repo_root / file_path), assertion, masked)

        port_lease = _acquire_port_lease()

        ctx = WorkerContext(
            worker_id=0,
            port=port_lease.port,
            project_name=f"reporeason_{uuid.uuid4().hex[:8]}",
            repo_path=repo_root,
            opencode_config=OPENCODE_CONFIG_PATH,
        )
        client = OpenCodeClient(ctx)

        try:
            client.start()
            session = client.create_session(f"inspect-reporeason-{state.sample_id}")
            session_id = session.get("id")
            if not isinstance(session_id, str) or not session_id:
                raise RuntimeError("OpenCode session did not return an id")

            prompt = render_task_prompt(
                file_path=file_path,
                masked_statement=masked,
                repo_dir=_effective_repo_dir(repo_dir),
            )
            prompt = _rewrite_prompt_repo_path(prompt, str(repo_root))
            prompt = "Return strict JSON only.\n" + prompt

            model_event, model_call = _start_model_event(
                transcript_obj,
                model=str(state.model),
                prompt=prompt,
                request={
                    "provider": "opencode",
                    "session_id": session_id,
                    "agent": "plan",
                },
            )
            _ = _send_opencode_message(
                ctx,
                session_id,
                prompt,
                model=str(state.model),
                agent="plan",
            )

            tool_events: dict[str, ToolEvent] = {}

            def _on_poll_first() -> None:
                messages = client.fetch_messages(session_id)
                _emit_tool_events(transcript_obj, messages, tool_events)
                latest_text = _extract_last_assistant_text(messages)
                _update_model_event(
                    transcript_obj,
                    event=model_event,
                    model=str(state.model),
                    text=_sanitize_assistant_text(latest_text or ""),
                )

            messages_payload = _wait_for_assistant_messages(
                client,
                session_id,
                max_assistant_repeats=DEFAULT_MAX_ASSISTANT_REPEATS,
                on_poll=_on_poll_first,
            )
            loop_guard: dict[str, Any] | None = None
            repeat_count = _assistant_repeat_count(messages_payload)
            if (
                DEFAULT_MAX_ASSISTANT_REPEATS > 0
                and repeat_count >= DEFAULT_MAX_ASSISTANT_REPEATS
            ):
                loop_guard = {
                    "max_assistant_repeats": DEFAULT_MAX_ASSISTANT_REPEATS,
                    "repeats": repeat_count,
                    "triggered": True,
                }

            # If the first response already contains valid JSON, skip the
            # follow-up nudge — sending the prompt again would produce a
            # duplicate answer.
            first_text = _extract_last_assistant_text(messages_payload)
            if loop_guard is None and not (
                first_text and parse_json_output(first_text)
            ):
                model_event, model_call = _start_model_event(
                    transcript_obj,
                    model=str(state.model),
                    prompt=_build_final_prompt(prompt),
                    request={
                        "provider": "opencode",
                        "session_id": session_id,
                    },
                )
                _ = _send_opencode_message(
                    ctx,
                    session_id,
                    _build_final_prompt(prompt),
                    model=str(state.model),
                )
                tool_events = {}

                def _on_poll_final() -> None:
                    messages = client.fetch_messages(session_id)
                    _emit_tool_events(transcript_obj, messages, tool_events)
                    latest_text = _extract_last_assistant_text(messages)
                    _update_model_event(
                        transcript_obj,
                        event=model_event,
                        model=str(state.model),
                        text=_sanitize_assistant_text(latest_text or ""),
                    )

                messages_payload = _wait_for_assistant_messages(
                    client,
                    session_id,
                    timeout=240.0,
                    poll_interval=2.0,
                    require_json=True,
                    max_assistant_repeats=DEFAULT_MAX_ASSISTANT_REPEATS,
                    on_poll=_on_poll_final,
                )
                if loop_guard is None:
                    repeat_count = _assistant_repeat_count(messages_payload)
                    if (
                        DEFAULT_MAX_ASSISTANT_REPEATS > 0
                        and repeat_count >= DEFAULT_MAX_ASSISTANT_REPEATS
                    ):
                        loop_guard = {
                            "max_assistant_repeats": DEFAULT_MAX_ASSISTANT_REPEATS,
                            "repeats": repeat_count,
                            "triggered": True,
                        }
            combined_messages = messages_payload
            chat_messages = _opencode_messages_to_chat(
                combined_messages,
                model=str(state.model),
                include_user=False,
            )
            if chat_messages:
                state.messages = [state.messages[0], *chat_messages]

            final_answer = None
            final_message_text = None
            input_text = _input_text_from_opencode_messages(combined_messages)
            fallback_text = _extract_last_assistant_text(combined_messages)
            if fallback_text:
                fallback_text = _sanitize_assistant_text(fallback_text)
                final_answer = parse_json_output(fallback_text)
                final_message_text = fallback_text

            completion = final_message_text
            if not completion and final_answer:
                completion = json.dumps(final_answer)
            if not completion:
                debug_path = ensure_runs_root() / f"opencode_debug_{session_id}.json"
                debug_payload = {
                    "sample_id": state.sample_id,
                    "session_id": session_id,
                    "messages": combined_messages,
                }
                debug_path.write_text(
                    json.dumps(debug_payload, indent=2, ensure_ascii=True),
                    encoding="utf-8",
                )
            if loop_guard is None:
                repeat_count = _assistant_repeat_count(combined_messages)
                if (
                    DEFAULT_MAX_ASSISTANT_REPEATS > 0
                    and repeat_count >= DEFAULT_MAX_ASSISTANT_REPEATS
                ):
                    loop_guard = {
                        "max_assistant_repeats": DEFAULT_MAX_ASSISTANT_REPEATS,
                        "repeats": repeat_count,
                        "triggered": True,
                    }
            usage = _extract_usage_from_messages(combined_messages)
            output = ModelOutput.from_content(
                model=str(state.model),
                content=completion or "",
            )
            if usage:
                output.usage = usage
                record_and_check_model_usage(str(state.model), usage)
            _finalize_model_event(
                transcript_obj,
                event=model_event,
                call=model_call,
                model=str(state.model),
                completion=completion or "",
                response={
                    "provider": "opencode",
                    "session_id": session_id,
                    "messages": combined_messages,
                },
            )
            state.output = output
            metadata = {
                **(state.metadata or {}),
                "opencode": {
                    "session_id": session_id,
                    "repo_url": repo_url,
                    "repo_commit_id": commit_id,
                },
                "io_stats": {
                    "input": _text_stats(input_text),
                    "output": _text_stats(completion or ""),
                },
            }
            if loop_guard:
                metadata["loop_guard"] = loop_guard
            state.metadata = metadata
            return state
        finally:
            client.stop()
            shutil.rmtree(repo_root, ignore_errors=True)
            port_lease.release()

    async def solve(state, generate):
        transcript_obj = transcript()
        return await asyncio.to_thread(_solve_sync, state, transcript_obj)

    return solve


# ---------------------------------------------------------------------------
# Task entry point
# ---------------------------------------------------------------------------


@task
def reporeason(
    dataset_path: str = DEFAULT_DATASET_PATH,
    repo_dir: str = DEFAULT_REPO_DIR,
) -> Task:
    dataset = load_dataset(dataset_path, repo_dir=repo_dir)
    return Task(
        dataset=dataset,
        solver=[opencode_solver(repo_dir=repo_dir)],
        scorer=repo_reason_scorer(),
        approval=[
            ApprovalPolicy(approver=readonly_approver(), tools="bash"),
        ],
    )
