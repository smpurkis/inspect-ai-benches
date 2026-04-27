"""Shared host-side infrastructure for terminal-bench single-step tasks.

Convention:
  - Each benchmark lives in terminal-bench/<challenge-name>/
  - Visible files are in <challenge-name>/files/ (injected into /app/files/)
  - Hidden test data is in <challenge-name>/hidden/ (injected into /app/hidden/)
  - files/instructions.md contains the task prompt
  - files/tests.py (visible) and hidden/hidden_tests.py (hidden)

Usage in a per-task run.py:
    from staged_eval import create_task

    @task
    def run():
        return create_task(challenge_dir=Path(__file__).resolve().parent)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from inspect_ai import Task
from inspect_ai.model import ChatMessageUser
from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer, stderr
from inspect_ai.solver import Generate, Solver, solver, use_tools
from inspect_ai.tool import bash, python
from inspect_ai.util import sandbox

from inspect_cyber import create_agentic_eval_dataset
from inspect_evals.harbor.harbor import _convert_sandbox_for_local_build


# ---------------------------------------------------------------------------
# Output file paths (inside the container)
# ---------------------------------------------------------------------------

REWARD_FILE = "/var/tmp/reward.txt"
STATUS_FILE = "/logs/verifier/stage_status.txt"
DETAILS_FILE = "/logs/verifier/stage_details.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discover_steps(challenge_dir: Path) -> list[int]:
    """For terminal-bench flat layout, always returns [1] if files/ exists."""
    if (challenge_dir / "files").is_dir():
        return [1]
    return []


def _extract_test_counts(result_line: str) -> tuple[int, int]:
    """Parse pytest result line into (passed_count, total_count).

    Example: '= 12 passed, 2 failed in 5.43s =' → (12, 14)
    """
    passed = failed = errors = 0
    for m in re.finditer(r"(\d+)\s+(passed|failed|error)", result_line):
        n = int(m.group(1))
        if m.group(2) == "passed":
            passed = n
        elif m.group(2) == "failed":
            failed = n
        else:
            errors = n
    return passed, passed + failed + errors


def _parse_pytest_output(stdout_text: str) -> dict:
    """Parse raw pytest stdout into a structured summary."""
    lines = stdout_text.splitlines()
    summary_lines: list[str] = []
    failed_tests: list[str] = []
    failure_blocks: list[str] = []

    capture = False
    for line in lines:
        if "short test summary info" in line.lower():
            capture = True
            continue
        if capture:
            if line.strip() == "":
                capture = False
                continue
            summary_lines.append(line)
            if line.strip().startswith("FAILED "):
                failed_tests.append(line.strip())

    passed_line = ""
    for line in reversed(lines):
        s = line.strip()
        if " passed" in s or " failed" in s or " error" in s:
            if " in " in s:
                passed_line = s
                break

    capture_block = False
    current_block: list[str] = []
    for line in lines:
        if line.startswith("___") and "___" in line[3:]:
            if current_block:
                failure_blocks.append("\n".join(current_block))
                current_block = []
            capture_block = True
        if capture_block:
            current_block.append(line)
            if line.startswith("===") and "short test summary info" in line.lower():
                capture_block = False
                if current_block:
                    failure_blocks.append("\n".join(current_block))
                    current_block = []
    if current_block:
        failure_blocks.append("\n".join(current_block))

    passed_count, total_count = _extract_test_counts(passed_line)

    return {
        "failed_tests": failed_tests,
        "short_summary": "\n".join(summary_lines[-12:]),
        "result_line": passed_line,
        "passed_count": passed_count,
        "total_count": total_count,
        "output_head": "\n".join(lines[:25]),
        "output_tail": "\n".join(lines[-25:]),
        "failure_details": "\n\n".join(failure_blocks[:4]),
    }


def _format_score_explanation(status_content: str, details_json: dict) -> str:
    """Format stage details into readable text for the score explanation."""
    out = [status_content.strip()]
    steps = (details_json or {}).get("steps", {})
    for step_name in sorted(steps):
        step = steps.get(step_name) or {}
        gate = step.get("gate_result", "not_run")
        if gate == "not_run":
            continue
        out.append(f"{step_name}: {gate}")
        out.append(f"  command: {step.get('gate_command', '')}")
        pytest_info = step.get("pytest") or {}
        result_line = pytest_info.get("result_line")
        if result_line:
            out.append(f"  result: {result_line}")
        failed = pytest_info.get("failed_tests") or []
        if failed:
            out.append("  failed_tests:")
            for item in failed[:6]:
                out.append(f"    - {item}")
        failure_details = pytest_info.get("failure_details") or ""
        if failure_details:
            out.append("  failure_details:")
            for ln in failure_details.splitlines()[:80]:
                out.append(f"    {ln}")
        step_stderr = step.get("stderr") or ""
        if step_stderr.strip():
            out.append("  stderr:")
            for ln in step_stderr.splitlines()[:40]:
                out.append(f"    {ln}")
    return "\n".join(out)


def _stage_pytest_shell(
    *,
    test_files: list[str],
    ctrf_path: str | None = None,
    verbose: bool = True,
) -> str:
    """Build a shell command that prefers /app/.venv pytest and uses CTRF if available."""
    quoted_tests = " ".join(test_files)
    verbosity = "-vv -rA" if verbose else "-rA"
    ctrf_stmt = (
        f'if "$PYTEST_PY" -m pytest --help 2>/dev/null | grep -q -- "--ctrf"; then CTRF_ARGS="--ctrf {ctrf_path}"; fi; '
        if ctrf_path
        else ""
    )
    return (
        'PYTEST_PY="python3"; '
        'if [ -x /app/.venv/bin/python ]; then PYTEST_PY="/app/.venv/bin/python"; fi; '
        'CTRF_ARGS=""; '
        f"{ctrf_stmt}"
        f'"$PYTEST_PY" -m pytest {verbosity} --timeout=900 $CTRF_ARGS {quoted_tests}'
    )


# ---------------------------------------------------------------------------
# Staged unlock solver
# ---------------------------------------------------------------------------


@solver
def staged_unlock_solver(
    host_steps_dir: Path,
    bash_timeout: int = 900,
    test_timeout: int = 1200,
    writable_patterns: list[str] | None = None,
) -> Solver:
    """Single-step solver for terminal-bench flat layout.

    Flat structure: <challenge>/files/ → /app/files/  and  <challenge>/hidden/ → /app/hidden/

    1. Inject visible files (files/) into /app/files/
    2. Prompt the agent to read /app/files/instructions.md and work
    3. Inject hidden files (hidden/) into /app/hidden/ and run pytest
    4. Remove hidden files

    Args:
        host_steps_dir: Path to the challenge directory (contains files/ and hidden/).
        writable_patterns: Glob patterns relative to files/ for agent-editable files.
    """
    tools_solver = use_tools(bash(timeout=bash_timeout), python(timeout=300))
    # host_steps_dir IS the challenge_dir for the flat layout
    challenge_dir = host_steps_dir
    steps = _discover_steps(challenge_dir)
    _writable = writable_patterns or []

    async def _run(cmd: str, timeout: int = 120) -> int:
        result = await sandbox().exec(["bash", "-lc", cmd], timeout=timeout)
        return result.returncode

    async def _write_reward(value: float) -> None:
        await sandbox().write_file(REWARD_FILE, f"{value:.6f}")

    async def _write_status(step_results: dict[int, bool]) -> None:
        lines = [
            f"stage{s}={'pass' if step_results.get(s, False) else 'fail'}"
            for s in steps
        ]
        await sandbox().write_file(STATUS_FILE, "\n".join(lines) + "\n")

    async def _write_details(details: dict) -> None:
        await sandbox().write_file(DETAILS_FILE, json.dumps(details, indent=2))

    async def _inject_visible(_step: int) -> None:
        """Write visible files into /app/files/ in the container.

        Files already present (Docker bind mounts) are skipped.
        After writing, every file is made read-only except writable_patterns.
        """
        files_dir = challenge_dir / "files"
        if not files_dir.exists():
            return
        container_root = "/app/files"
        # Ensure top-level destination exists
        await _run(f"mkdir -p {container_root}", timeout=10)
        for host_file in files_dir.rglob("*"):
            if not host_file.is_file():
                continue
            if "__pycache__" in host_file.parts or host_file.suffix == ".pyc":
                continue
            rel = host_file.relative_to(files_dir)
            target = f"{container_root}/{rel.as_posix()}"
            # Ensure parent directory exists in container
            parent_dir = str(Path(target).parent)
            if parent_dir != container_root:
                await _run(f"mkdir -p {parent_dir}", timeout=10)
            check = await sandbox().exec(["test", "-f", target])
            if check.returncode == 0:
                continue
            try:
                await sandbox().write_file(target, host_file.read_bytes())
            except Exception:
                pass

        # Lock down: make all files read-only, keep directories writable.
        await _run(
            f"find {container_root} -type f -exec chmod a-w {{}} + 2>/dev/null; true",
            timeout=10,
        )
        # Restore write permission for agent-editable files.
        for pattern in _writable:
            await _run(
                f"chmod a+w {container_root}/{pattern} 2>/dev/null; true",
                timeout=10,
            )

    async def _inject_hidden(_step: int) -> None:
        """Write hidden files into /app/hidden/ in the container."""
        hidden_dir = challenge_dir / "hidden"
        if not hidden_dir.exists():
            return
        await _remove_hidden(_step)
        await _run("mkdir -p /app/hidden", timeout=10)
        for host_file in hidden_dir.rglob("*"):
            if not host_file.is_file():
                continue
            if "__pycache__" in host_file.parts or host_file.suffix == ".pyc":
                continue
            rel = host_file.relative_to(hidden_dir)
            target = f"/app/hidden/{rel.as_posix()}"
            # Ensure parent directory exists
            parent_dir = str(Path(target).parent)
            if parent_dir != "/app/hidden":
                await _run(f"mkdir -p {parent_dir}", timeout=10)
            await sandbox().write_file(target, host_file.read_bytes())
        # Make hidden test files read-only during the test window.
        await _run(
            "find /app/hidden -type f -exec chmod a-w {} + 2>/dev/null; true",
            timeout=10,
        )

    async def _remove_hidden(_step: int) -> None:
        """Remove /app/hidden from the container."""
        await _run("rm -rf /app/hidden", timeout=120)

    async def _run_stage_tests(
        step: int, details: dict
    ) -> tuple[bool, int, int]:
        """Inject hidden, run pytest, remove hidden.

        Returns (ok, passed_count, total_count).
        """
        step_key = f"step{step}"

        gate_cmd = _stage_pytest_shell(
            test_files=[
                "/app/files/tests.py",
                "/app/hidden/hidden_tests.py",
            ],
            ctrf_path="/logs/verifier/ctrf.json",
        )
        details["steps"][step_key]["gate_command"] = gate_cmd

        await _inject_hidden(step)

        try:
            result = await sandbox().exec(
                ["bash", "-lc", gate_cmd], timeout=test_timeout
            )
            stdout_text = (
                result.stdout if isinstance(result.stdout, str) else str(result.stdout)
            )
            stderr_text = (
                result.stderr if isinstance(result.stderr, str) else str(result.stderr)
            )
            details["steps"][step_key]["returncode"] = result.returncode
            pytest_info = _parse_pytest_output(stdout_text)
            details["steps"][step_key]["pytest"] = pytest_info
            details["steps"][step_key]["stderr"] = stderr_text[:2000]
            ok = result.returncode == 0
            details["steps"][step_key]["gate_result"] = "pass" if ok else "fail"
            await _write_details(details)
            passed_count = pytest_info.get("passed_count", 0)
            total_count = pytest_info.get("total_count", 0)
            return ok, passed_count, total_count
        finally:
            await _remove_hidden(step)

    async def solve(state, generate: Generate):
        total = len(steps)
        reward = 0.0
        step_results: dict[int, bool] = {}
        details: dict = {
            "steps": {f"step{s}": {"gate_result": "not_run"} for s in steps}
        }

        await _run("mkdir -p /logs/verifier", timeout=120)
        await _write_reward(0.0)
        await _write_status(step_results)
        await _write_details(details)

        state = await tools_solver(state, generate)

        for idx, step in enumerate(steps):
            await _inject_visible(step)

            prompt = (
                f"{state.input_text}\n\n"
                "Read /app/files/instructions.md for full task details. "
                "When done, provide a short completion note."
            )

            state.completed = False
            state.messages.append(ChatMessageUser(content=prompt))
            state = await generate(state, tool_calls="loop")

            ok, passed_count, total_count = await _run_stage_tests(
                step, details
            )
            step_results[step] = ok

            if ok:
                reward += 1.0 / total
            else:
                # Partial credit: proportion of tests passed
                if total_count > 0:
                    reward += (1.0 / total) * (passed_count / total_count)
                await _write_reward(reward)
                await _write_status(step_results)
                state.completed = True
                return state

            await _write_reward(reward)
            await _write_status(step_results)

        state.completed = True
        return state

    return solve


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


@scorer(metrics=[accuracy(), stderr()])
def staged_scorer(
    reward_file: str = REWARD_FILE,
    status_file: str = STATUS_FILE,
    details_file: str = DETAILS_FILE,
) -> Scorer:
    """Reads reward/status/details written by staged_unlock_solver."""

    async def score(state, target: Target) -> Score:
        try:
            reward_content = await sandbox().read_file(reward_file)
            reward_value = float(reward_content.strip())
        except (ValueError, FileNotFoundError):
            reward_value = 0.0

        try:
            status_content = await sandbox().read_file(status_file)
        except FileNotFoundError:
            status_content = "stage1=fail\n"

        details_json: dict | None = None
        try:
            details_content = await sandbox().read_file(details_file)
            details_json = json.loads(details_content)
        except (FileNotFoundError, json.JSONDecodeError):
            details_json = None

        explanation = status_content
        if details_json:
            explanation = _format_score_explanation(status_content, details_json)

        return Score(
            value=reward_value,
            answer="PASS" if reward_value > 0 else "FAIL",
            explanation=explanation,
            metadata={
                "stage_status": status_content,
                "stage_details": details_json,
            },
        )

    return score


# ---------------------------------------------------------------------------
# Task factory
# ---------------------------------------------------------------------------


def create_task(
    *,
    challenge_dir: Path,
    variant_names: str | list[str] | None = "default",
    bash_timeout: int = 900,
    test_timeout: int = 1200,
    writable_patterns: list[str] | None = None,
) -> Task:
    """Build a staged-unlock eval task from a challenge directory.

    Args:
        challenge_dir: Path to the specific challenge (e.g. closed-terminal-bench/cifar10-burn-optimise/)
        variant_names: Which eval.yaml variant(s) to use for the initial prompt
        bash_timeout: Max seconds for each agent bash tool call
        test_timeout: Max seconds for each step's pytest gate
        writable_patterns: File patterns the agent may edit (everything else is
            read-only).  Patterns are relative to each step's files/ directory.
    """
    challenge_dir = challenge_dir.resolve()
    challenges_root = challenge_dir.parent
    # Flat layout: files/ and hidden/ live directly under challenge_dir
    host_steps_dir = challenge_dir

    # Scope the dataset scan to just this challenge directory so we don't
    # try to resolve file paths from other benchmarks' eval.yaml files.
    dataset = create_agentic_eval_dataset(
        root_dir=challenge_dir
    ).filter_by_metadata_field("variant_name", variant_names)
    # _convert_sandbox_for_local_build expects the parent (challenges root)
    # because it joins challenges_root / eval_name internally.
    dataset = dataset.flat_map(_convert_sandbox_for_local_build(challenges_root))

    return Task(
        dataset=dataset,
        solver=staged_unlock_solver(
            host_steps_dir=host_steps_dir,
            bash_timeout=bash_timeout,
            test_timeout=test_timeout,
            writable_patterns=writable_patterns,
        ),
        scorer=staged_scorer(),
    )
