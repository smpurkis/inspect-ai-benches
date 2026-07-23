"""Policy-mediated tools backed by Harbor's ``BaseEnvironment`` API."""

from __future__ import annotations

import asyncio
import base64
from collections import Counter
from dataclasses import dataclass, field
import json
from math import ceil
from pathlib import Path
import posixpath
import shlex
import tempfile
from time import monotonic
from typing import Any, Awaitable, Callable

try:
    from .budget import BudgetState, TaskContract, parse_public_test_argv
    from .tool_policy import (
        ActionClass,
        action_cost,
        editable_fingerprint,
        forbidden_import,
        is_editable_path,
        is_output_path,
        normalize_command,
        normalize_test_feedback,
        posix_glob_match,
        read_cache_key,
        relative_app_files_path,
        search_cache_key,
        validate_app_files_path,
    )
    from .usage import USAGE_SCHEMA_VERSION, UsageEvent, UsageTrace
except ImportError:  # Support legacy PYTHONPATH=god-bench/common usage.
    from budget import BudgetState, TaskContract, parse_public_test_argv
    from tool_policy import (
        ActionClass,
        action_cost,
        editable_fingerprint,
        forbidden_import,
        is_editable_path,
        is_output_path,
        normalize_command,
        normalize_test_feedback,
        posix_glob_match,
        read_cache_key,
        relative_app_files_path,
        search_cache_key,
        validate_app_files_path,
    )
    from usage import USAGE_SCHEMA_VERSION, UsageEvent, UsageTrace


USAGE_FILE = "/logs/agent/agent_usage.json"
ARTIFACT_ROOT = "/logs/artifacts/god-bench"
ARTIFACT_USAGE_FILE = f"{ARTIFACT_ROOT}/agent_usage.json"
ARTIFACT_FILES_ROOT = f"{ARTIFACT_ROOT}/files"
PUBLIC_TOOL_LOG = "/logs/agent/public_tool_latest.log"
MAX_TOOL_CHARS = 8_000
MAX_SEARCH_RESULTS = 20
MAX_READ_LINES = 500
MAX_READ_BYTES = 64_000
MAX_EDITABLE_ARTIFACT_BYTES = 2_000_000
MAX_TOTAL_ARTIFACT_BYTES = 8_000_000


def _return_code(result: Any) -> int:
    return int(getattr(result, "return_code", getattr(result, "returncode", 1)))


def _text(value: Any) -> str:
    return "" if value is None else value if isinstance(value, str) else str(value)


async def _upload_bytes(environment: Any, target: str, value: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "payload"
        source.write_bytes(value)
        await environment.upload_file(source, target)


async def _download_bytes(environment: Any, source: str) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "payload"
        await environment.download_file(source, target)
        return target.read_bytes()


@dataclass(slots=True)
class ToolDefinition:
    """OpenAI-compatible tool schema and its single mediated implementation."""

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Awaitable[str]]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(slots=True)
class StrictToolRuntime:
    """Synchronized accounting and Harbor environment operations for strict tools."""

    contract: TaskContract
    budget: BudgetState
    environment: Any
    trace: UsageTrace = field(default_factory=UsageTrace)
    build_timeout: int = 900
    test_timeout: int = 1200
    provider_cost_usd: float = 0.0
    provider_usage_valid: bool = True
    model_cache_tokens: int = 0
    _read_cache: dict[tuple[str, int | None, int | None], int] = field(default_factory=dict)
    _search_cache: dict[tuple[bytes, str, int], int] = field(default_factory=dict)
    _command_fingerprints: dict[str, str] = field(default_factory=dict)
    _class_counts: Counter[str] = field(default_factory=Counter)
    _final_public_used: bool = False
    _action_started: float = field(default=0.0, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def _exec(self, command: str, *, timeout: int = 30) -> Any:
        return await self.environment.exec(command, timeout_sec=timeout)

    async def _canonical_existing(self, path: str) -> str:
        validated = validate_app_files_path(path)
        result = await self._exec(f"realpath -e -- {shlex.quote(validated)}", timeout=10)
        if _return_code(result) != 0:
            raise ValueError("path does not exist")
        canonical = _text(result.stdout).strip()
        return validate_app_files_path(canonical)

    async def _listed_files(self, root: str = "/app/files") -> list[str]:
        result = await self._exec(
            f"find {shlex.quote(root)} -type f -print", timeout=30
        )
        if _return_code(result) != 0:
            return []
        return [line for line in _text(result.stdout).splitlines() if line]

    async def _editable_files(self) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        total_size = 0
        for path in await self._listed_files():
            try:
                canonical = await self._canonical_existing(path)
                if canonical != path or not is_editable_path(path, self.contract.editable):
                    continue
                if is_output_path(path, self.contract.outputs):
                    continue
                size_result = await self._exec(
                    f"stat -c %s -- {shlex.quote(path)}", timeout=10
                )
                if _return_code(size_result) != 0:
                    continue
                size = int(_text(size_result.stdout).strip())
                if size > MAX_EDITABLE_ARTIFACT_BYTES:
                    raise RuntimeError("editable artifact exceeds per-file size limit")
                total_size += size
                if total_size > MAX_TOTAL_ARTIFACT_BYTES:
                    raise RuntimeError("editable artifacts exceed total size limit")
                files[relative_app_files_path(path)] = await _download_bytes(
                    self.environment, path
                )
            except (FileNotFoundError, ValueError):
                continue
        return files

    async def fingerprint(self) -> str:
        return editable_fingerprint(await self._editable_files())

    def _cost(self, action: ActionClass) -> int:
        return action_cost(action, self._class_counts[action.value])

    def _remaining_timeout(self, configured: int) -> int | None:
        remaining = self.contract.budget.wall_clock_seconds - self.budget.elapsed()
        return None if remaining <= 0 else min(configured, max(1, ceil(remaining)))

    def _relevance(self, relative_path: str) -> bool | None:
        if not self.contract.context.enabled:
            return None
        return any(
            posix_glob_match(relative_path, pattern)
            for pattern in self.contract.context.patterns
        )

    def _reserve(self, *, cost: int, public_runs: int = 0, read_bytes: int = 0) -> bool:
        if not self.budget.permits(
            weighted_tool_cost=cost,
            public_test_runs=public_runs,
            file_read_bytes=read_bytes,
        ):
            return False
        self.budget.apply(
            weighted_tool_cost=cost,
            public_test_runs=public_runs,
            file_read_bytes=read_bytes,
        )
        return True

    async def _record(
        self,
        *,
        tool: str,
        command: str,
        action: ActionClass,
        cost: int,
        output: str,
        input_chars: int = 0,
        read_bytes: int = 0,
        before: str = "",
        after: str = "",
        no_progress: bool = False,
        observed_path: str | None = None,
        relevant: bool | None = None,
    ) -> str:
        if cost:
            self._class_counts[action.value] += 1
        self.trace.append(
            UsageEvent(
                turn=self.budget.turns,
                tool=tool,
                normalized_command=normalize_command(command),
                action_class=action.value,
                tool_cost=cost,
                input_chars=input_chars,
                output_chars=len(output),
                read_bytes=read_bytes,
                editable_fingerprint_before=before,
                editable_fingerprint_after=after,
                no_progress=no_progress,
                elapsed_seconds=self.budget.elapsed(),
                duration_seconds=max(0.0, monotonic() - self._action_started),
                observed_path=observed_path,
                relevant=relevant,
            )
        )
        await self.write_usage()
        return output

    async def _deny(
        self,
        tool: str,
        command: str,
        action: ActionClass,
        reason: str,
        *,
        cost: int = 0,
        before: str = "",
        no_progress: bool = False,
    ) -> str:
        return await self._record(
            tool=tool,
            command=command,
            action=action,
            cost=cost,
            output=f"DENIED: {reason}"[:MAX_TOOL_CHARS],
            input_chars=len(command),
            before=before,
            after=before,
            no_progress=no_progress,
        )

    def usage_artifact(self, now: float | None = None) -> dict[str, Any]:
        current = monotonic() if now is None else now
        self.trace.elapsed_seconds = self.budget.elapsed(current)
        return {
            "schema_version": USAGE_SCHEMA_VERSION,
            "trace": self.trace.as_dict(),
            "budget": self.budget.config.as_dict(),
            "budget_snapshot": self.budget.as_dict(current),
            "public_test_count": self.budget.public_test_runs,
            "within_budget": self.budget.within_budget(current),
            "provider_cost_usd": self.provider_cost_usd,
            "provider_usage_valid": self.provider_usage_valid,
            "model_cache_tokens": self.model_cache_tokens,
        }

    async def write_usage(self) -> None:
        payload = json.dumps(self.usage_artifact(), indent=2, sort_keys=True).encode()
        await self._exec("mkdir -p /logs/agent /logs/artifacts/god-bench", timeout=10)
        await _upload_bytes(self.environment, USAGE_FILE, payload)
        await _upload_bytes(self.environment, ARTIFACT_USAGE_FILE, payload)

    async def search(self, query: str, path: str = "/app/files") -> str:
        async with self._lock:
            self._action_started = monotonic()
            command = f"rg {query!r} {path!r}"
            if self.budget.in_finalization_mode:
                return await self._deny("strict_search", command, ActionClass.SEARCH, "search is disabled in finalization mode")
            if not isinstance(query, str) or not query:
                return await self._deny("strict_search", command, ActionClass.SEARCH, "query cannot be empty")
            try:
                canonical = await self._canonical_existing(path)
            except ValueError as error:
                return await self._deny("strict_search", command, ActionClass.SEARCH, str(error))
            key = search_cache_key(query, canonical, MAX_SEARCH_RESULTS)
            if key in self._search_cache:
                return await self._record(
                    tool="strict_search", command=command, action=ActionClass.SEARCH,
                    cost=0, output=f"Cached: identical search already returned at tool call {self._search_cache[key]}. 0 budget charged.",
                )
            timeout = self._remaining_timeout(30)
            if timeout is None:
                return await self._deny("strict_search", command, ActionClass.SEARCH, "agent wall-clock budget has no time remaining")
            cost = self._cost(ActionClass.SEARCH)
            if not self._reserve(cost=cost):
                return await self._deny("strict_search", command, ActionClass.SEARCH, "prospective budget limit")
            result = await self._exec(
                "rg --line-number --no-heading --color never --max-columns 1000 "
                f"--max-columns-preview -- {shlex.quote(query)} {shlex.quote(canonical)}",
                timeout=timeout,
            )
            lines = _text(result.stdout).splitlines()[:MAX_SEARCH_RESULTS]
            output = "\n".join(lines)[:MAX_TOOL_CHARS]
            successful = _return_code(result) in {0, 1}
            if not output:
                output = "No matches." if successful else "Search failed."
            if successful:
                self._search_cache[key] = len(self.trace.events) + 1
            return await self._record(
                tool="strict_search", command=command, action=ActionClass.SEARCH,
                cost=cost, output=output, input_chars=len(query) + len(path),
            )

    async def read(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        async with self._lock:
            self._action_started = monotonic()
            end_line = start_line + 199 if end_line is None else end_line
            command = f"read {path!r} {start_line}:{end_line}"
            try:
                read_cache_key(path, start_line, end_line)
            except (TypeError, ValueError) as error:
                return await self._deny("strict_read", command, ActionClass.READ, str(error))
            oversize = end_line - start_line + 1 > MAX_READ_LINES
            action = ActionClass.OVERSIZE_READ if oversize else ActionClass.READ
            if self.budget.in_finalization_mode:
                return await self._deny("strict_read", command, action, "read is disabled in finalization mode")
            try:
                canonical = await self._canonical_existing(path)
            except ValueError as error:
                return await self._deny("strict_read", command, action, str(error))
            key = read_cache_key(canonical, start_line, end_line)
            if key in self._read_cache:
                return await self._record(
                    tool="strict_read", command=command, action=ActionClass.READ, cost=0,
                    output=f"Cached: identical read already returned at tool call {self._read_cache[key]}. 0 budget charged.",
                )
            remaining = self.contract.budget.max_file_read_bytes - self.budget.file_read_bytes
            timeout = self._remaining_timeout(30)
            if remaining <= 0 or timeout is None:
                return await self._deny("strict_read", command, action, "prospective read-byte or wall-clock budget limit")
            cap = min(MAX_READ_BYTES, remaining)
            script = (
                "import base64,json,sys; p,s,e,c=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]);"
                "d=b''.join(open(p,'rb').readlines()[s-1:e]);"
                "print(json.dumps({'data':base64.b64encode(d[:c]).decode(),'truncated':len(d)>c}))"
            )
            result = await self._exec(
                "python3 -c " + shlex.quote(script) + " " + " ".join(
                    shlex.quote(item) for item in (canonical, str(start_line), str(min(end_line, start_line + MAX_READ_LINES - 1)), str(cap))
                ),
                timeout=timeout,
            )
            if _return_code(result) != 0:
                return await self._deny("strict_read", command, action, "file range could not be read")
            try:
                payload = json.loads(_text(result.stdout))
                selected = base64.b64decode(payload["data"], validate=True)
                output = selected.decode("utf-8")
                truncated = payload["truncated"] is True
            except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                return await self._deny("strict_read", command, action, "file range is not valid UTF-8 text")
            suffix = "\n[output capped]"
            if oversize or truncated or len(output) > MAX_TOOL_CHARS:
                output = output[: MAX_TOOL_CHARS - len(suffix)] + suffix
                action = ActionClass.OVERSIZE_READ
            read_bytes = len(output.removesuffix(suffix).encode())
            cost = self._cost(action)
            if not self._reserve(cost=cost, read_bytes=read_bytes):
                return await self._deny("strict_read", command, action, "prospective budget limit")
            self._read_cache[key] = len(self.trace.events) + 1
            observed = relative_app_files_path(canonical)
            return await self._record(
                tool="strict_read", command=command, action=action, cost=cost,
                output=output, input_chars=len(command), read_bytes=read_bytes,
                observed_path=observed, relevant=self._relevance(observed),
            )

    async def edit(self, path: str, old_text: str, new_text: str) -> str:
        async with self._lock:
            self._action_started = monotonic()
            command = f"edit {path!r} old={len(old_text)} new={len(new_text)}"
            try:
                absolute = validate_app_files_path(path)
                relative = relative_app_files_path(absolute)
            except (TypeError, ValueError) as error:
                return await self._deny("strict_edit", command, ActionClass.EDIT, str(error))
            if not is_editable_path(absolute, self.contract.editable):
                return await self._deny("strict_edit", command, ActionClass.EDIT, "path is not contract-editable")
            before = await self.fingerprint()
            link = await self._exec(f"test -L {shlex.quote(absolute)}", timeout=10)
            if _return_code(link) == 0:
                return await self._deny("strict_edit", command, ActionClass.EDIT, "symlink edit destinations are not allowed", before=before)
            exists = await self._exec(f"test -f {shlex.quote(absolute)}", timeout=10)
            if _return_code(exists) == 0:
                try:
                    canonical = await self._canonical_existing(absolute)
                    if canonical != absolute:
                        raise ValueError("edit destination is not canonical")
                    current = (await _download_bytes(self.environment, absolute)).decode("utf-8")
                except (UnicodeDecodeError, ValueError):
                    return await self._deny("strict_edit", command, ActionClass.EDIT, "existing file is unsafe or not UTF-8", before=before)
                if not old_text:
                    return await self._deny("strict_edit", command, ActionClass.EDIT, "old_text must be non-empty for an existing file", before=before)
                count = current.count(old_text)
                if count != 1:
                    return await self._deny("strict_edit", command, ActionClass.EDIT, f"old_text must match exactly once (found {count})", before=before)
                updated = current.replace(old_text, new_text, 1)
            else:
                if old_text:
                    return await self._deny("strict_edit", command, ActionClass.EDIT, "new files require empty old_text", before=before)
                parent = posixpath.dirname(absolute)
                ancestor = parent
                while ancestor != "/app/files":
                    if _return_code(await self._exec(f"test -L {shlex.quote(ancestor)}", timeout=10)) == 0:
                        return await self._deny("strict_edit", command, ActionClass.EDIT, "unsafe parent directory", before=before)
                    ancestor = posixpath.dirname(ancestor)
                made = await self._exec(f"mkdir -p -- {shlex.quote(parent)}", timeout=10)
                if _return_code(made) != 0:
                    return await self._deny("strict_edit", command, ActionClass.EDIT, "could not create parent directory", before=before)
                updated = new_text
            denied = forbidden_import(updated, self.contract.policy.forbid_imports)
            if denied:
                return await self._deny("strict_edit", command, ActionClass.EDIT, f"forbidden import: {denied}", before=before)
            cost = self._cost(ActionClass.EDIT)
            if not self._reserve(cost=cost):
                return await self._deny("strict_edit", command, ActionClass.EDIT, "prospective budget limit", before=before)
            await _upload_bytes(self.environment, absolute, updated.encode())
            self._read_cache.clear()
            self._search_cache.clear()
            after = await self.fingerprint()
            return await self._record(
                tool="strict_edit", command=command, action=ActionClass.EDIT, cost=cost,
                output=f"Edited {relative}; fingerprint {before[:12]} -> {after[:12]}.",
                input_chars=len(path) + len(old_text) + len(new_text), before=before, after=after,
            )

    async def _run_trusted(self, *, public: bool) -> str:
        self._action_started = monotonic()
        tool = "run_public_tests" if public else "strict_build"
        action = ActionClass.PUBLIC_TEST if public else ActionClass.BUILD
        command = self.contract.public_test if public else self.contract.build
        if not command:
            return await self._deny(tool, "", action, "no command is declared")
        if (not public and self.budget.in_finalization_mode) or (public and self.budget.in_finalization_mode and self._final_public_used):
            return await self._deny(tool, command, action, "command is disabled in finalization mode")
        before = await self.fingerprint()
        normalized = normalize_command(command)
        if self._command_fingerprints.get(normalized) == before:
            self.budget.apply(no_progress_retries=1)
            retry_cost = action_cost(ActionClass.NO_PROGRESS)
            if not self._reserve(cost=retry_cost):
                retry_cost = 0
            return await self._deny(tool, command, ActionClass.NO_PROGRESS, "identical build/test without an editable change", cost=retry_cost, before=before, no_progress=True)
        timeout = self._remaining_timeout(self.test_timeout if public else self.build_timeout)
        if timeout is None:
            return await self._deny(tool, command, action, "agent wall-clock budget has no time remaining", before=before)
        cost = self._cost(action)
        if not self._reserve(cost=cost, public_runs=int(public)):
            return await self._deny(tool, command, action, "prospective budget limit", before=before)
        self._command_fingerprints[normalized] = before
        if public:
            argv = parse_public_test_argv(command)
            execution = " ".join(shlex.quote(value) for value in argv)
            if self.budget.in_finalization_mode:
                self._final_public_used = True
        else:
            execution = command
        process_baseline = await self._snapshot_pids()
        try:
            result = await self._exec(execution, timeout=timeout)
            returncode = _return_code(result)
            stdout, stderr = _text(result.stdout), _text(result.stderr)
        except TimeoutError:
            returncode, stdout, stderr = 124, "", "trusted command timed out"
        finally:
            await self._cleanup_new_processes(process_baseline)
        if public:
            await _upload_bytes(self.environment, PUBLIC_TOOL_LOG, (stdout + "\n" + stderr)[:40_000].encode())
            output = json.dumps(normalize_test_feedback(stdout, stderr, returncode=returncode), separators=(",", ":"))
        else:
            feedback = normalize_test_feedback(stdout, stderr, returncode=returncode)
            output = json.dumps({"ok": returncode == 0, "failure_category": feedback["failure_category"]}, separators=(",", ":"))
        after = await self.fingerprint()
        return await self._record(
            tool=tool, command=command, action=action, cost=cost, output=output,
            input_chars=len(command), before=before, after=after,
        )

    async def build(self) -> str:
        async with self._lock:
            return await self._run_trusted(public=False)

    async def public_test(self) -> str:
        async with self._lock:
            return await self._run_trusted(public=True)

    async def _snapshot_pids(self) -> set[int]:
        result = await self._exec("ps -e -o pid=", timeout=10)
        if _return_code(result) != 0:
            raise RuntimeError("could not snapshot candidate processes")
        pids = {int(value) for value in _text(result.stdout).split() if value.isdigit()}
        if not pids:
            raise RuntimeError("candidate process snapshot was empty")
        return pids

    async def _cleanup_new_processes(self, baseline: set[int]) -> None:
        script = (
            "import os,signal\nbaseline={"
            + ",".join(str(pid) for pid in sorted(baseline))
            + "}\nprotected={1,os.getpid(),os.getppid()}\n"
            "for value in os.listdir('/proc'):\n"
            "    if not value.isdigit(): continue\n"
            "    pid=int(value)\n"
            "    if pid in baseline|protected: continue\n"
            "    try: os.kill(pid,signal.SIGKILL)\n"
            "    except (ProcessLookupError,PermissionError): pass\n"
        )
        result = await self._exec("python3 -c " + shlex.quote(script), timeout=30)
        if _return_code(result) != 0:
            raise RuntimeError("could not terminate candidate-created processes")

    def definitions(self) -> list[ToolDefinition]:
        object_schema = {"type": "object", "additionalProperties": False}
        return [
            ToolDefinition("strict_search", "Bounded ripgrep search under /app/files.", {**object_schema, "properties": {"query": {"type": "string"}, "path": {"type": "string", "default": "/app/files"}}, "required": ["query"]}, self.search),
            ToolDefinition("strict_read", "Read a bounded UTF-8 line range under /app/files.", {**object_schema, "properties": {"path": {"type": "string"}, "start_line": {"type": "integer", "minimum": 1}, "end_line": {"type": "integer", "minimum": 1}}, "required": ["path"]}, self.read),
            ToolDefinition("strict_edit", "Replace exactly one text occurrence in a contract-editable file.", {**object_schema, "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}, self.edit),
            ToolDefinition("strict_build", "Run only the contract's trusted build command.", {**object_schema, "properties": {}}, self.build),
            ToolDefinition("run_public_tests", "Run only the contract's exact public test command.", {**object_schema, "properties": {}}, self.public_test),
        ]

    async def publish_editables(self) -> None:
        await self._exec(f"rm -rf -- {shlex.quote(ARTIFACT_FILES_ROOT)} && mkdir -p -- {shlex.quote(ARTIFACT_FILES_ROOT)}", timeout=30)
        files = await self._editable_files()
        for relative, content in files.items():
            target = f"{ARTIFACT_FILES_ROOT}/{relative}"
            await self._exec(f"mkdir -p -- {shlex.quote(posixpath.dirname(target))}", timeout=10)
            await _upload_bytes(self.environment, target, content)


__all__ = [
    "ARTIFACT_FILES_ROOT",
    "ARTIFACT_ROOT",
    "ARTIFACT_USAGE_FILE",
    "MAX_READ_BYTES",
    "MAX_EDITABLE_ARTIFACT_BYTES",
    "MAX_TOTAL_ARTIFACT_BYTES",
    "MAX_READ_LINES",
    "MAX_SEARCH_RESULTS",
    "MAX_TOOL_CHARS",
    "StrictToolRuntime",
    "ToolDefinition",
    "USAGE_FILE",
]
