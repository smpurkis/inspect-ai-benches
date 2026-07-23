"""Pure normalization, classification, costing, and progress-policy helpers."""

from __future__ import annotations

from enum import StrEnum
import ast
import hashlib
import posixpath
import re
import shlex
from typing import Any, Mapping


class ActionClass(StrEnum):
    SEARCH = "search"
    READ = "read"
    EDIT = "edit"
    BUILD = "build"
    PUBLIC_TEST = "public_test"
    FULL_TEST = "full_test"
    NO_PROGRESS = "no_progress"
    OVERSIZE_READ = "oversize_read"
    OTHER = "other"


_SHELL_OPERATORS = {"|", "||", "&", "&&", ";", "<", ">", "<<", ">>", "(", ")"}


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def normalize_command(command: str) -> str:
    """Canonicalize shell whitespace and quoting without executing the command."""

    if not isinstance(command, str):
        raise TypeError("command must be a string")
    if not command.strip():
        return ""
    try:
        tokens = _shell_tokens(command)
    except ValueError:
        return " ".join(command.split())
    return " ".join(token if token in _SHELL_OPERATORS else shlex.quote(token) for token in tokens)


def normalize_query(query: str) -> str:
    """Canonicalize insignificant surrounding and repeated whitespace."""

    if not isinstance(query, str):
        raise TypeError("query must be a string")
    return " ".join(query.split())


def posix_glob_match(path: str, pattern: str) -> bool:
    """Match a POSIX path glob where ``*`` cannot cross a slash and ``**`` can."""

    if not isinstance(path, str) or not isinstance(pattern, str):
        raise TypeError("path and pattern must be strings")
    expression: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    expression.append("(?:[^/]+/)*")
                    index += 1
                else:
                    expression.append(".*")
                continue
            expression.append("[^/]*")
        elif character == "?":
            expression.append("[^/]")
        elif character == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                expression.append(r"\[")
            else:
                content = pattern[index + 1 : end]
                negate = content.startswith(("!", "^"))
                if negate:
                    content = content[1:]
                escaped = content.replace("\\", r"\\").replace("]", r"\]")
                expression.append("[^" if negate else "[")
                expression.append(escaped)
                expression.append("]")
                index = end
        else:
            expression.append(re.escape(character))
        index += 1
    expression.append("$")
    return re.fullmatch("".join(expression), path) is not None


def _command_words(command: str) -> list[str]:
    try:
        tokens = _shell_tokens(command)
    except ValueError:
        return command.split()
    return [token for token in tokens if token not in _SHELL_OPERATORS]


def classify_action(
    command: str,
    *,
    public_test_command: str | None = None,
) -> ActionClass:
    """Classify a controlled command into the strict weighted-cost schedule."""

    normalized = normalize_command(command)
    if public_test_command is not None and normalized == normalize_command(public_test_command):
        return ActionClass.PUBLIC_TEST

    words = _command_words(command)
    if not words:
        return ActionClass.OTHER
    executable = posixpath.basename(words[0]).lower()
    arguments = " ".join(words[1:]).lower()

    if executable in {"rg", "grep", "find", "fd", "ls"}:
        return ActionClass.SEARCH
    if executable in {"cat", "head", "tail", "less", "more"}:
        return ActionClass.READ
    if executable in {"apply_patch", "patch", "touch", "mkdir", "cp", "mv", "rm"}:
        return ActionClass.EDIT

    if executable in {"pytest", "py.test"} or (
        executable in {"python", "python3"} and "-m pytest" in f" {arguments}"
    ):
        if "hidden" in arguments or not any(
            marker in arguments for marker in ("tests_public", "/files/tests.py", " files/tests.py")
        ):
            return ActionClass.FULL_TEST
        return ActionClass.PUBLIC_TEST

    if executable in {
        "make",
        "cmake",
        "ninja",
        "cargo",
        "go",
        "ruff",
        "mypy",
        "pyright",
        "flake8",
        "gcc",
        "g++",
        "clang",
        "clang++",
    }:
        return ActionClass.BUILD
    if executable in {"npm", "pnpm", "yarn"} and any(
        verb in words[1:] for verb in ("build", "test", "lint")
    ):
        return ActionClass.BUILD
    if executable in {"train", "torchrun"} or "train.py" in executable:
        return ActionClass.FULL_TEST
    return ActionClass.OTHER


def action_cost(action: ActionClass | str, prior_count: int = 0) -> int:
    """Return the cost of the next action given its prior class invocation count."""

    try:
        action_class = ActionClass(action)
    except ValueError as error:
        raise ValueError(f"unknown action class: {action!r}") from error
    if isinstance(prior_count, bool) or not isinstance(prior_count, int):
        raise TypeError("prior_count must be an integer")
    if prior_count < 0:
        raise ValueError("prior_count cannot be negative")

    if action_class is ActionClass.SEARCH:
        return 2 if prior_count >= 8 else 1
    if action_class is ActionClass.READ:
        return 2 if prior_count >= 12 else 1
    if action_class is ActionClass.EDIT:
        return 1
    if action_class is ActionClass.BUILD:
        return 3 if prior_count >= 5 else 2
    if action_class is ActionClass.PUBLIC_TEST:
        return 8 if prior_count >= 2 else 5
    if action_class is ActionClass.FULL_TEST:
        return 13 if prior_count >= 1 else 8
    if action_class is ActionClass.NO_PROGRESS:
        return 8
    if action_class is ActionClass.OVERSIZE_READ:
        return 6
    return 1


def editable_fingerprint(files: Mapping[str, bytes | str]) -> str:
    """Return a deterministic SHA-256 digest of editable paths and contents."""

    digest = hashlib.sha256()
    for path in sorted(files):
        content = files[path]
        if not isinstance(path, str):
            raise TypeError("editable file paths must be strings")
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            raise TypeError("editable file contents must be bytes or strings")
        path_bytes = path.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content_bytes).to_bytes(8, "big"))
        digest.update(content_bytes)
    return digest.hexdigest()


def _normalize_path(path: str) -> str:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    return posixpath.normpath(path.strip() or ".")


def validate_app_files_path(path: str) -> str:
    """Return an absolute lexical path confined to ``/app/files``."""

    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if not path.strip() or "\x00" in path or "\\" in path:
        raise ValueError("path is empty or contains an unsafe character")
    candidate = path.strip()
    if not candidate.startswith("/"):
        candidate = posixpath.join("/app/files", candidate)
    normalized = posixpath.normpath(candidate)
    if normalized != "/app/files" and not normalized.startswith("/app/files/"):
        raise ValueError("path must remain under /app/files")
    return normalized


def relative_app_files_path(path: str) -> str:
    """Validate a path and return its name relative to ``/app/files``."""

    absolute = validate_app_files_path(path)
    if absolute == "/app/files":
        return "."
    return absolute.removeprefix("/app/files/")


def is_editable_path(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Match a validated path against contract-relative editable globs."""

    relative = relative_app_files_path(path)
    return any(posix_glob_match(relative, pattern) for pattern in patterns)


def is_output_path(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Return whether an app-files path is a declared generated output."""

    absolute = validate_app_files_path(path)
    return any(posix_glob_match(absolute, validate_app_files_path(pattern)) for pattern in patterns)


def forbidden_import(content: str, modules: tuple[str, ...] | list[str]) -> str | None:
    """Return the first contract-forbidden Python import found in source text."""

    if not modules:
        return None
    imported: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
    # Cython files may not parse as Python but retain Python-like import syntax.
    imported.extend(
        match.group(1)
        for match in re.finditer(
            r"^\s*(?:from|import|cimport)\s+([A-Za-z_]\w*(?:\.\w+)*)",
            content,
            re.MULTILINE,
        )
    )
    for name in imported:
        for denied in modules:
            if name == denied or name.startswith(f"{denied}."):
                return denied
    return None


def normalize_test_feedback(
    stdout: str,
    stderr: str = "",
    *,
    returncode: int = 1,
) -> dict[str, Any]:
    """Produce compact public-test feedback without leaking full raw logs."""

    text = f"{stdout}\n{stderr}".strip()
    result_line = ""
    for line in reversed(text.splitlines()):
        if re.search(r"\b\d+\s+(?:passed|failed|error|errors)\b", line):
            result_line = line.strip()
            break
    counts = {"passed": 0, "failed": 0, "error": 0}
    for count, kind in re.findall(r"(\d+)\s+(passed|failed|error|errors)\b", result_line):
        counts["error" if kind.startswith("error") else kind] += int(count)
    total = sum(counts.values())
    passed = counts["passed"]
    if returncode == 0 and total == 0:
        passed = total = 1

    lowered = text.lower()
    if returncode == 0:
        category = "pass"
    elif "timeout" in lowered or "timed out" in lowered:
        category = "timeout"
    elif "error collecting" in lowered or "collection error" in lowered:
        category = "collection_error"
    elif "assertionerror" in lowered or re.search(r"^\s*assert\s", text, re.MULTILINE):
        category = "assertion"
    elif "syntaxerror" in lowered or "importerror" in lowered or "modulenotfounderror" in lowered:
        category = "runtime_error"
    else:
        category = "test_failure"

    assertion = ""
    location = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not location:
            match = re.search(r"((?:/app/files/)?[^\s:]+\.(?:py|rs|wat|pyx)):(\d+)", stripped)
            if match:
                location = f"{match.group(1)}:{match.group(2)}"
        if not assertion and (
            "AssertionError" in stripped or stripped.startswith("E       assert ")
        ):
            assertion = stripped[:300]
        if assertion and location:
            break
    return {
        "passed": passed,
        "total": total,
        "failure_category": category,
        "assertion": assertion,
        "location": location,
    }


def read_cache_key(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> tuple[str, int | None, int | None]:
    """Build a canonical key for a file-range observation."""

    for name, value in (("start_line", start_line), ("end_line", end_line)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise TypeError(f"{name} must be an integer or None")
        if value is not None and value < 1:
            raise ValueError(f"{name} must be at least 1")
    if start_line is not None and end_line is not None and end_line < start_line:
        raise ValueError("end_line cannot precede start_line")
    return (_normalize_path(path), start_line, end_line)


def search_cache_key(
    query: str,
    path: str = ".",
    max_results: int = 20,
) -> tuple[bytes, str, int]:
    """Build a canonical key for a bounded search observation."""

    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise TypeError("max_results must be an integer")
    if max_results <= 0:
        raise ValueError("max_results must be greater than zero")
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    return (query.encode("utf-8"), _normalize_path(path), max_results)


def is_no_progress_test(
    command: str,
    editable_fingerprint_value: str,
    *,
    previous_command: str | None,
    previous_editable_fingerprint: str | None,
    public_test_command: str | None = None,
) -> bool:
    """Detect an identical test/build command with no intervening editable change."""

    action = classify_action(command, public_test_command=public_test_command)
    if action not in {ActionClass.BUILD, ActionClass.PUBLIC_TEST, ActionClass.FULL_TEST}:
        return False
    if previous_command is None or previous_editable_fingerprint is None:
        return False
    return (
        normalize_command(command) == normalize_command(previous_command)
        and editable_fingerprint_value == previous_editable_fingerprint
    )
