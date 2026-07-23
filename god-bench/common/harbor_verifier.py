"""Native Harbor verifier for isolated, correctness-gated GOD-Bench grading."""

from __future__ import annotations

import json
from pathlib import Path
import posixpath
import secrets
import shlex
import tempfile
from typing import Any

from harbor.models.task.config import NetworkMode
from harbor.models.verifier.result import VerifierResult
from harbor.verifier.base import BaseVerifier

from .budget import load_task_contract, parse_public_test_argv
from .budgeted_tools import ARTIFACT_FILES_ROOT, ARTIFACT_USAGE_FILE
from .budgeted_tools import MAX_EDITABLE_ARTIFACT_BYTES, MAX_TOTAL_ARTIFACT_BYTES
from .tool_policy import (
    is_editable_path,
    is_output_path,
    normalize_test_feedback,
    relative_app_files_path,
    validate_app_files_path,
)
from .usage import summarize_usage_artifact


METADATA_FILE = "/logs/verifier/god_bench_metadata.json"
PLUGIN_ROOT = "/app/.god-bench-verifier-plugin"
PLUGIN_FILE = f"{PLUGIN_ROOT}/god_bench_order.py"


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


def _pytest_counts(stdout: str, stderr: str, returncode: int) -> tuple[int, int]:
    feedback = normalize_test_feedback(stdout, stderr, returncode=returncode)
    return int(feedback["passed"]), int(feedback["total"])


class GodBenchVerifier(BaseVerifier):
    """Rebuild pristine inputs and verify a narrow candidate overlay offline."""

    def __init__(
        self,
        *,
        files_subdir: str = "files",
        hidden_subdir: str = "hidden",
        hidden_test: str = "hidden_tests.py",
        build_timeout: int = 900,
        test_timeout: int = 1200,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.files_subdir = files_subdir
        self.hidden_subdir = hidden_subdir
        self.hidden_test = hidden_test
        self.build_timeout = build_timeout
        self.test_timeout = test_timeout

    def _source_dirs(self) -> tuple[Path, Path]:
        files = (self.task.task_dir / self.files_subdir).resolve()
        hidden = (self.task.task_dir / self.hidden_subdir).resolve()
        root = self.task.task_dir.resolve()
        if not files.is_relative_to(root) or not hidden.is_relative_to(root):
            raise RuntimeError("verifier source directories escape the task")
        if not files.is_dir() or files.is_symlink():
            raise RuntimeError("pristine files directory is missing or unsafe")
        if not hidden.is_dir() or hidden.is_symlink():
            raise RuntimeError("hidden tests directory is missing or unsafe")
        for source_root in (files, hidden):
            for path in source_root.rglob("*"):
                if path.is_symlink():
                    raise RuntimeError(f"verifier source cannot be a symlink: {path}")
        return files, hidden

    async def _require_offline(self) -> None:
        policy = getattr(self.environment, "network_policy", None)
        if policy is None or policy.network_mode != NetworkMode.NO_NETWORK:
            raise RuntimeError("GOD-Bench verification requires a no-network verifier environment")
        task_config = getattr(self.task, "config", None)
        if task_config is None:
            return
        from harbor.models.task.config import VerifierEnvironmentMode
        from harbor.models.task.verifier_mode import (
            resolve_step_verifier_mode,
            resolve_task_verifier_mode,
        )

        if self.step_name is None:
            mode = resolve_task_verifier_mode(task_config)
        else:
            step = next(
                (item for item in task_config.steps or [] if item.name == self.step_name),
                None,
            )
            if step is None:
                raise RuntimeError("verifier step is not present in task config")
            mode = resolve_step_verifier_mode(task_config, step)
        if mode != VerifierEnvironmentMode.SEPARATE:
            raise RuntimeError("GOD-Bench verification requires Harbor separate mode")

    async def _reset_pristine(self, files: Path) -> None:
        result = await self.environment.empty_dirs(["/app/files"], chmod=True)
        if result is not None and _return_code(result) != 0:
            raise RuntimeError("could not reset verifier files")
        await self.environment.upload_dir(files, "/app/files")

    async def _overlay_candidates(self, contract: Any) -> list[str]:
        symlinks = await self.environment.exec(
            f"find {shlex.quote(ARTIFACT_FILES_ROOT)} -type l -print",
            timeout_sec=30,
        )
        if _return_code(symlinks) == 0 and _text(symlinks.stdout).strip():
            raise RuntimeError("candidate artifact contains a symlink")
        listed = await self.environment.exec(
            f"find {shlex.quote(ARTIFACT_FILES_ROOT)} -type f -print",
            timeout_sec=30,
        )
        if _return_code(listed) != 0:
            return []
        copied: list[str] = []
        total_size = 0
        prefix = ARTIFACT_FILES_ROOT + "/"
        for source in sorted(line for line in _text(listed.stdout).splitlines() if line):
            if not source.startswith(prefix):
                raise RuntimeError("candidate artifact escaped its root")
            relative = source.removeprefix(prefix)
            destination = validate_app_files_path(relative)
            if not is_editable_path(destination, contract.editable):
                continue
            if is_output_path(destination, contract.outputs):
                continue
            canonical = await self.environment.exec(
                f"realpath -e -- {shlex.quote(source)}", timeout_sec=10
            )
            if _return_code(canonical) != 0 or _text(canonical.stdout).strip() != source:
                raise RuntimeError("candidate artifact path is not canonical")
            size_result = await self.environment.exec(
                f"stat -c %s -- {shlex.quote(source)}", timeout_sec=10
            )
            if _return_code(size_result) != 0:
                raise RuntimeError("candidate artifact size could not be read")
            size = int(_text(size_result.stdout).strip())
            if size > MAX_EDITABLE_ARTIFACT_BYTES:
                raise RuntimeError("candidate artifact exceeds per-file size limit")
            total_size += size
            if total_size > MAX_TOTAL_ARTIFACT_BYTES:
                raise RuntimeError("candidate artifacts exceed total size limit")
            parent = posixpath.dirname(destination)
            made = await self.environment.exec(
                f"mkdir -p -- {shlex.quote(parent)}", timeout_sec=10
            )
            if _return_code(made) != 0:
                raise RuntimeError("could not create candidate parent")
            await _upload_bytes(
                self.environment,
                destination,
                await _download_bytes(self.environment, source),
            )
            copied.append(relative_app_files_path(destination))
        return copied

    async def _run(self, command: str, timeout: int) -> tuple[int, str, str]:
        try:
            result = await self.environment.exec(command, timeout_sec=timeout)
            return _return_code(result), _text(result.stdout), _text(result.stderr)
        except TimeoutError:
            return 124, "", "timed out"

    async def _snapshot_pids(self) -> set[int]:
        result = await self.environment.exec("ps -e -o pid=", timeout_sec=10)
        if _return_code(result) != 0:
            raise RuntimeError("could not snapshot verifier processes")
        pids = {
            int(value)
            for value in _text(result.stdout).split()
            if value.isdigit()
        }
        if not pids:
            raise RuntimeError("verifier process snapshot was empty")
        return pids

    async def _cleanup_new_processes(self, baseline: set[int]) -> None:
        script = (
            "import os,signal\nbaseline={"
            + ",".join(str(pid) for pid in sorted(baseline))
            + "}\nprotected={1,os.getpid(),os.getppid()}\n"
            "for value in os.listdir('/proc'):\n"
            "    if not value.isdigit():\n"
            "        continue\n"
            "    pid=int(value)\n"
            "    if pid in baseline|protected:\n"
            "        continue\n"
            "    try:\n"
            "        os.kill(pid,signal.SIGKILL)\n"
            "    except (ProcessLookupError,PermissionError):\n"
            "        pass\n"
        )
        result = await self.environment.exec(
            "python3 -c " + shlex.quote(script), timeout_sec=30
        )
        if _return_code(result) != 0:
            raise RuntimeError("could not terminate candidate-created processes")

    async def _run_candidate(
        self, command: str, timeout: int
    ) -> tuple[int, str, str]:
        baseline = await self._snapshot_pids()
        try:
            return await self._run(command, timeout)
        finally:
            await self._cleanup_new_processes(baseline)

    async def _read_usage(self) -> dict[str, Any] | None:
        try:
            return json.loads((await _download_bytes(self.environment, ARTIFACT_USAGE_FILE)).decode())
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    async def _write_metadata(self, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, indent=2, sort_keys=True)
        self.trial_paths.verifier_dir.mkdir(parents=True, exist_ok=True)
        (self.trial_paths.verifier_dir / Path(METADATA_FILE).name).write_text(
            payload, encoding="utf-8"
        )
        try:
            await self.environment.ensure_dirs(["/logs/verifier"], chmod=True)
            await _upload_bytes(self.environment, METADATA_FILE, payload.encode())
        except Exception:
            self.logger.warning("could not mirror GOD-Bench metadata into verifier environment")

    async def verify(self) -> VerifierResult:
        safe: dict[str, Any] = {
            "functional_pass": False,
            "public_pass_fraction": 0.0,
            "hidden_pass_fraction": 0.0,
            "failure_category": "verifier_error",
        }
        usage_artifact: dict[str, Any] | None = None
        cleanup_needed = False
        try:
            await self._require_offline()
            cleanup_needed = True
            files, hidden = self._source_dirs()
            contract = load_task_contract(self.task.task_dir, strict=True)
            usage_artifact = await self._read_usage()
            if (
                usage_artifact is not None
                and usage_artifact.get("budget") != contract.budget.as_dict()
            ):
                usage_artifact = None
            await self._reset_pristine(files)
            copied = await self._overlay_candidates(contract)
            safe["overlaid_files"] = copied

            if contract.build:
                build_rc, build_out, build_err = await self._run_candidate(
                    contract.build, self.build_timeout
                )
                if build_rc != 0:
                    safe["failure_category"] = normalize_test_feedback(
                        build_out, build_err, returncode=build_rc
                    )["failure_category"]
                    raise _VerificationFailed

            public_command = " ".join(
                shlex.quote(value) for value in parse_public_test_argv(contract.public_test)
            )
            public_rc, public_out, public_err = await self._run_candidate(
                public_command, self.test_timeout
            )
            public_passed, public_total = _pytest_counts(
                public_out, public_err, public_rc
            )
            safe["public_pass_fraction"] = (
                public_passed / public_total if public_total else float(public_rc == 0)
            )
            public_feedback = normalize_test_feedback(
                public_out, public_err, returncode=public_rc
            )
            safe["public_failure_category"] = public_feedback["failure_category"]

            hidden_result = await self.environment.empty_dirs(["/app/hidden"], chmod=True)
            if hidden_result is not None and _return_code(hidden_result) != 0:
                raise RuntimeError("could not reset hidden test directory")
            await self.environment.upload_dir(hidden, "/app/hidden")
            seed = secrets.randbits(64)
            safe["hidden_order_seed"] = seed
            plugin = (
                "import random\n"
                f"SEED = {seed}\n"
                "def pytest_collection_modifyitems(session, config, items):\n"
                "    random.Random(SEED).shuffle(items)\n"
            )
            await self.environment.ensure_dirs([PLUGIN_ROOT], chmod=True)
            await _upload_bytes(self.environment, PLUGIN_FILE, plugin.encode())
            hidden_path = validate_app_files_path(
                f"/app/files/{self.hidden_test}"
            ).replace("/app/files/", "/app/hidden/", 1)
            hidden_command = (
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(PLUGIN_ROOT)} "
                "python3 -m pytest -p no:cacheprovider -p god_bench_order "
                f"-q --tb=no --disable-warnings {shlex.quote(hidden_path)}"
            )
            hidden_rc, hidden_out, hidden_err = await self._run_candidate(
                hidden_command, self.test_timeout
            )
            hidden_passed, hidden_total = _pytest_counts(hidden_out, hidden_err, hidden_rc)
            safe["hidden_pass_fraction"] = (
                hidden_passed / hidden_total if hidden_total else float(hidden_rc == 0)
            )
            functional_pass = public_rc == 0 and hidden_rc == 0
            safe["functional_pass"] = functional_pass
            safe["failure_category"] = (
                "pass"
                if functional_pass
                else public_feedback["failure_category"]
                if public_rc != 0
                else normalize_test_feedback("", "hidden test failure", returncode=hidden_rc)[
                    "failure_category"
                ]
            )
        except _VerificationFailed:
            pass
        except TimeoutError:
            safe["failure_category"] = "timeout"
        except Exception as error:
            self.logger.warning("GOD-Bench verification failed closed: %s", error)
        finally:
            if cleanup_needed:
                try:
                    await self.environment.exec(
                        f"rm -rf -- /app/hidden {shlex.quote(PLUGIN_ROOT)}", timeout_sec=30
                    )
                except Exception:
                    self.logger.warning("could not clean verifier-only hidden files")

        usage = summarize_usage_artifact(
            usage_artifact, functional_pass=safe["functional_pass"] is True
        )
        metadata = {**safe, **usage}
        await self._write_metadata(metadata)
        correctness = int(safe["functional_pass"] is True)
        return VerifierResult(
            rewards={
                "reward": correctness,
                "correctness": correctness,
                "efficiency": float(usage["efficiency_score"]),
                "weighted_tool_cost": int(usage["weighted_tool_cost"]),
                "model_tokens": int(usage["model_total_tokens"]),
                "file_read_bytes": int(usage["file_read_bytes"]),
                "public_test_runs": int(usage["public_test_runs"]),
                "within_budget": int(usage["within_budget"] is True),
                "usage_valid": int(usage["usage_valid"] is True),
            }
        )


class _VerificationFailed(Exception):
    pass


__all__ = ["GodBenchVerifier", "METADATA_FILE"]
