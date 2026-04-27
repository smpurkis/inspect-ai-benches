"""Approval policy that only allows read-only bash commands."""

from __future__ import annotations

import re
import json
import os
from typing import Any

from inspect_ai.approval import Approval, approver
from inspect_ai.model._chat_message import ChatMessage
from inspect_ai.tool._tool_call import ToolCall, ToolCallView
from inspect_ai.util import store

from src.parsing import parse_json_output  # type: ignore

_DISALLOWED_PATTERNS = [
    r"\bpytest\b",
    r"\bpy\.test\b",
    r"\bpython\b",
    r"\bpython3\b",
    r"\btox\b",
    r"\bnox\b",
    r"\bnosetests\b",
    r"\bunittest\b",
    r"\bcoverage\b",
    r"\bmake\b\s+\btest\b",
    r"\bctest\b",
    r"\bpip\b",
    r"\bpoetry\b",
    r"\buv\b",
    r"\bnpm\b",
    r"\byarn\b",
    r"\bpnpm\b",
    r"\brm\b",
    r"\bmv\b",
    r"\bcp\b",
    r"\bmkdir\b",
    r"\btouch\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bln\b",
    r"\bsed\b\s+-i\b",
    r"\bperl\b\s+-i\b",
    r"\btruncate\b",
    r"\bdd\b",
]

_DISALLOWED_REGEX = re.compile("|".join(_DISALLOWED_PATTERNS))
_GIT_REGEX = re.compile(r"\bgit\b\s+([\w-]+)")
_ALLOWED_GIT = {"log", "show", "diff", "grep", "status"}
_MAX_TOOL_REPEATS = int(
    os.getenv(
        "REPOREASON_MAX_TOOL_REPEATS",
        os.getenv("REPOREASON_MAX_ASSISTANT_REPEATS", "5"),
    )
)


def _extract_cmd(arguments: Any) -> str | None:
    if isinstance(arguments, dict):
        for key in ("cmd", "command", "input"):
            value = arguments.get(key)
            if isinstance(value, str):
                return value
    return None


def _reject(reason: str) -> Approval:
    return Approval(decision="reject", explanation=reason)


class RepeatedToolCallError(RuntimeError):
    pass


def _normalize_repeat_text(text: str) -> str:
    return " ".join(text.split()).strip()


_HEREDOC_JSON = re.compile(
    r"cat\s+<<\s*['\"]?(?P<tag>[^\s'\"]+)['\"]?\s*\n(?P<body>.*?)\n(?P=tag)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_json_from_command(cmd: str) -> str | None:
    if not cmd:
        return None
    match = _HEREDOC_JSON.search(cmd)
    if match:
        candidate = (match.group("body") or "").strip()
        parsed = parse_json_output(candidate)
        if parsed:
            return json.dumps(parsed, ensure_ascii=True)
    parsed = parse_json_output(cmd)
    if parsed:
        return json.dumps(parsed, ensure_ascii=True)
    return None


def _record_tool_repeat(signature: str) -> int:
    state = store()
    last_signature = state.get("loop_guard.last_tool_signature")
    repeats = state.get("loop_guard.tool_repeats", 0)
    if signature and signature == last_signature:
        repeats += 1
    else:
        repeats = 1
    state.set("loop_guard.last_tool_signature", signature)
    state.set("loop_guard.tool_repeats", repeats)
    return repeats


@approver(name="readonly")
def readonly_approver() -> Any:
    async def approve(
        message: str,
        call: ToolCall,
        view: ToolCallView,
        history: list[ChatMessage],
    ) -> Approval:
        if call.function != "bash":
            return Approval(decision="approve", explanation="Non-bash tool allowed.")

        cmd = _extract_cmd(call.arguments)
        if not cmd:
            return _reject("Missing bash command.")

        candidate = _extract_json_from_command(cmd)
        if candidate:
            state = store()
            state.set("loop_guard.triggered", True)
            state.set("loop_guard.max_tool_repeats", _MAX_TOOL_REPEATS)
            state.set("loop_guard.repeats", 1)
            state.set("loop_guard.last_tool_command", cmd)
            state.set("loop_guard.last_tool_json", candidate)
            state.set("loop_guard.tool_json_detected", True)
            raise RepeatedToolCallError("Final JSON provided via tool call.")

        signature = _normalize_repeat_text(cmd)
        if _MAX_TOOL_REPEATS > 0:
            repeats = _record_tool_repeat(signature)
            if repeats >= _MAX_TOOL_REPEATS:
                state = store()
                candidate = _extract_json_from_command(cmd)
                state.set("loop_guard.triggered", True)
                state.set("loop_guard.max_tool_repeats", _MAX_TOOL_REPEATS)
                state.set("loop_guard.repeats", repeats)
                state.set("loop_guard.last_tool_command", cmd)
                if candidate:
                    state.set("loop_guard.last_tool_json", candidate)
                raise RepeatedToolCallError("Repeated tool call loop detected.")

        if _DISALLOWED_REGEX.search(cmd):
            return _reject("Write or test execution is not allowed.")

        git_match = _GIT_REGEX.search(cmd)
        if git_match and git_match.group(1) not in _ALLOWED_GIT:
            return _reject("Only read-only git commands are allowed.")

        return Approval(decision="approve", explanation="Read-only bash allowed.")

    return approve
