"""Shared JSON parsing utilities for reporeason benchmark."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

_JSON_FENCE = re.compile(r"```json(.*?)```", re.IGNORECASE | re.DOTALL)
_HEREDOC_JSON = re.compile(
    r"cat\s+<<\s*['\"]?(?P<tag>[^\s'\"]+)['\"]?\s*\n(?P<body>.*?)\n(?P=tag)",
    re.IGNORECASE | re.DOTALL,
)
_JSON_KV_RE = re.compile(
    r"\"(?P<key>reason|answer)\"\s*:\s*\"(?P<value>(?:\\.|[^\"])*)\"",
    re.IGNORECASE | re.DOTALL,
)


def normalize_target_value(value: Any) -> str | list[str]:
    if value is None:
        return ""
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value)


def parse_json_output(text: str) -> dict[str, Any] | None:
    """Extract a ``{"reason": ..., "answer": ...}`` dict from model output."""
    if not text:
        return None

    # Try fenced JSON blocks (last one first).
    for block in reversed(_JSON_FENCE.findall(text)):
        parsed = _try_load_json(block.strip())
        if parsed:
            return parsed

    # Plain text that might start with ``json`` or be raw JSON.
    stripped = text.strip()
    candidates = [stripped]
    if stripped.lower().startswith("json"):
        candidates.append(stripped[4:].strip())
    for candidate in candidates:
        parsed = _try_load_json(candidate)
        if parsed:
            return parsed

    # Try heredoc JSON blocks (last one first).
    heredocs = list(_HEREDOC_JSON.finditer(text))
    for match in reversed(heredocs):
        candidate = (match.group("body") or "").strip()
        parsed = _try_load_json(candidate)
        if parsed:
            return parsed

    # Scan for JSON-like substrings containing reason/answer.
    for blob in _iter_json_substrings(text):
        parsed = _try_load_json(blob)
        if parsed:
            return parsed

    # Last-resort: recover individual key/value pairs from broken JSON.
    recovered = _recover_json_fields(text)
    if recovered:
        return recovered

    return None


def _try_load_json(blob: str) -> dict[str, Any] | None:
    if not blob:
        return None
    stripped = blob.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not {"reason", "answer"}.issubset(parsed.keys()):
        return None
    if not isinstance(parsed.get("reason"), str):
        return None
    if not isinstance(parsed.get("answer"), str):
        return None
    return parsed
    return None


def _iter_json_substrings(text: str) -> Iterable[str]:
    depth = 0
    start = None
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start : idx + 1]
                    start = None


def _recover_json_fields(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    reason_candidates: list[str] = []
    answer_candidates: list[str] = []
    for match in _JSON_KV_RE.finditer(text):
        key = (match.group("key") or "").lower()
        raw_value = match.group("value") or ""
        value = raw_value
        try:
            value = json.loads(f'"{raw_value}"')
        except json.JSONDecodeError:
            value = raw_value
        value = value.strip()
        if not value:
            continue
        if key == "reason":
            reason_candidates.append(value)
        elif key == "answer":
            answer_candidates.append(value)
    if not answer_candidates:
        return None
    reason = max(reason_candidates, key=len) if reason_candidates else ""
    if not reason:
        reason = "Recovered from streaming output."
    return {"reason": reason, "answer": answer_candidates[-1]}


def looks_like_streaming_json(text: str) -> bool:
    """Return True if text looks like an incomplete JSON stream."""
    if not text:
        return False
    brace_open = text.count("{")
    brace_close = text.count("}")
    if brace_open < 3:
        return False
    reason_hits = len(re.findall(r"\"reason\"", text, flags=re.IGNORECASE))
    answer_hits = len(re.findall(r"\"answer\"", text, flags=re.IGNORECASE))
    if reason_hits + answer_hits < 2:
        return False
    return brace_close < brace_open


def extract_final_json_object(text: str) -> dict[str, Any] | None:
    """Extract the last valid JSON object containing reason/answer."""
    if not text:
        return None
    parsed = parse_json_output(text)
    if parsed:
        return parsed
    for blob in reversed(list(_iter_json_substrings(text))):
        candidate = _try_load_json(blob)
        if candidate:
            return candidate
    anchor = text.rfind('"answer"')
    if anchor == -1:
        return None
    start = text.rfind("{", 0, anchor)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : idx + 1]
                return _try_load_json(candidate)
    return None
