"""Host-side infrastructure for running external agent harnesses (opencode, pi, etc.).

Instead of inspect-ai's generate loop, this runs an agent CLI inside the sandbox
and captures its stdout/stderr as the conversation. Scoring is identical to staged_eval.

Usage in a per-task run.py:
    from harness_eval import create_task

    @task
    def run():
        return create_task(challenge_dir=Path(__file__).resolve().parent)
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from inspect_ai import Task
from inspect_ai.model import ChatMessageAssistant, ChatMessageUser
from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer, stderr
from inspect_ai.solver import Generate, Solver, solver
from inspect_ai.util import sandbox

from inspect_cyber import create_agentic_eval_dataset
from _harbor_compat import _convert_sandbox_for_local_build

from staged_eval import (
    DETAILS_FILE,
    REWARD_FILE,
    STATUS_FILE,
    _extract_test_counts,
    _format_score_explanation,
    _parse_pytest_output,
    _stage_pytest_shell,
)

def _openai_env(base_url: str, api_key: str) -> dict[str, str]:
    return {"OPENAI_API_KEY": api_key, "OPENAI_BASE_URL": base_url}


# ---------------------------------------------------------------------------
# Harness builders — each returns (cmd, env_vars, config_file_content | None)
#
# config_file_content is written to a harness-specific path before running.
# Config paths are in HARNESS_CONFIG_PATHS below.
# ---------------------------------------------------------------------------

def _build_opencode(prompt, model, base_url, api_key):
    """opencode (npm opencode-ai) — .opencode.json with @ai-sdk/openai-compatible."""
    config = json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "bench": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "bench",
                "options": {"baseURL": base_url, "apiKey": api_key},
                "models": {
                    model: {"name": model, "limit": {"context": 128000, "output": 16384}},
                },
            },
        },
    })
    return ["opencode", "run", prompt], {}, config


def _build_pi(prompt, model, base_url, api_key):
    """pi (npm @mariozechner/pi-coding-agent) — models.json with custom provider."""
    config = json.dumps({
        "providers": {
            "bench": {
                "baseUrl": base_url, "api": "openai-completions",
                "apiKey": api_key,
                "models": [{"id": model, "contextWindow": 128000, "maxTokens": 16384}],
            },
        },
    })
    return ["pi", "--no-session", "--no-context-files", "--provider", "bench", "--model", model, "-p", prompt], {}, config


def _build_claude(prompt, model, base_url, api_key):
    """claude (npm @anthropic-ai/claude-code) — runs as non-root user 'agent'."""
    return (
        ["claude", "-p", "--dangerously-skip-permissions", "--model", model, prompt],
        {"ANTHROPIC_API_KEY": api_key, "ANTHROPIC_BASE_URL": base_url},
        None,
    )


def _build_codex(prompt, model, base_url, api_key):
    """codex (npm @openai/codex) — uses OPENAI env vars."""
    return (
        ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-m", model, prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_gemini(prompt, model, base_url, api_key):
    """gemini (google agents-cli) — uses GEMINI env vars."""
    return (
        ["gemini", "--yolo", "--model", model, prompt],
        {"GEMINI_API_KEY": api_key},
        None,
    )


def _build_cline(prompt, model, base_url, api_key):
    """cline (npm cline) — run `cline auth -p openai` first, then task.

    Cline appends /v1/ internally, so strip it from the base URL if present.
    """
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    setup_cmd = (
        f"cline auth -p openai -k {shlex.quote(api_key)}"
        f" -b {shlex.quote(url)} -m {shlex.quote(model)}"
    )
    return (
        ["bash", "-c", f"{setup_cmd} && cline task --yolo -m {shlex.quote(model)} {shlex.quote(prompt)}"],
        {},
        None,
    )


def _build_kilocode(prompt, model, base_url, api_key):
    """kilocode (npm kilocode) — uses OPENAI env vars."""
    return (
        ["kilocode", "run", "--auto", prompt, "-m", model],
        _openai_env(base_url, api_key),
        None,
    )


def _build_codebuff(prompt, model, base_url, api_key):
    """codebuff (npm codebuff) — needs login, uses OPENAI env vars."""
    return (
        ["codebuff", prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_goose(prompt, model, base_url, api_key):
    """goose (aaif-goose/goose) — uses OPENAI env vars + --provider openai."""
    return (
        ["goose", "run", "--no-session", "--provider", "openai", "--model", model, "-t", prompt],
        {**_openai_env(base_url, api_key), "GOOSE_MODE": "auto"},
        None,
    )


def _build_amp(prompt, model, base_url, api_key):
    """amp (sourcegraph) — uses OPENAI env vars."""
    return (
        ["amp", "--dangerously-allow-all", "-m", model, "-x", prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_kimi(prompt, model, base_url, api_key):
    """kimi — uses KIMI env vars."""
    return (
        ["kimi", "--yolo", "-m", model, "-c", prompt],
        {"KIMI_API_KEY": api_key},
        None,
    )


def _build_crush(prompt, model, base_url, api_key):
    """crush (charmbracelet, successor to opencode Go) — uses .opencode.json same as opencode."""
    config = json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "bench": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "bench",
                "options": {"baseURL": base_url, "apiKey": api_key},
                "models": {
                    model: {"name": model, "limit": {"context": 128000, "output": 16384}},
                },
            },
        },
    })
    return ["crush", "run", prompt], {}, config


def _build_copilot(prompt, model, base_url, api_key):
    """copilot (GitHub Copilot CLI) — requires GitHub auth."""
    return (
        ["copilot", "--allow-all-tools", "--model", model, "-i", prompt],
        {},
        None,
    )


def _build_droid(prompt, model, base_url, api_key):
    """droid (Factory) — uses OPENAI env vars."""
    return (
        ["droid", "exec", "--skip-permissions-unsafe", "-m", model, prompt],
        {**_openai_env(base_url, api_key), "CI": "true"},
        None,
    )


def _build_iflow(prompt, model, base_url, api_key):
    """iflow — uses OPENAI env vars."""
    return (
        ["iflow", "--yolo", "-m", model, "-p", prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_qwen(prompt, model, base_url, api_key):
    """qwen — uses OPENAI env vars."""
    return (
        ["qwen", "--yolo", "-m", model, prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_vibe(prompt, model, base_url, api_key):
    """vibe (Mistral) — uses OPENAI env vars."""
    return (
        ["vibe", "--prompt", prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_forge(prompt, model, base_url, api_key):
    """forge — uses OPENAI env vars."""
    return (
        ["forge", "--model", model, "-p", prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_junie(prompt, model, base_url, api_key):
    """junie (JetBrains) — uses OPENAI env vars."""
    return (
        ["junie", "--skip-update-check", "--model", model, "--task", prompt],
        _openai_env(base_url, api_key),
        None,
    )


def _build_ccs(prompt, model, base_url, api_key):
    """ccs (Claude Code Squad) — uses ANTHROPIC env vars."""
    return (
        ["ccs", "--dangerously-skip-permissions", model, prompt],
        {"ANTHROPIC_API_KEY": api_key, "ANTHROPIC_BASE_URL": base_url},
        None,
    )


HARNESSES: dict[str, callable] = {
    "opencode": _build_opencode,
    "pi": _build_pi,
    "claude": _build_claude,
    "codex": _build_codex,
    "gemini": _build_gemini,
    "cline": _build_cline,
    "kilocode": _build_kilocode,
    "codebuff": _build_codebuff,
    "goose": _build_goose,
    "amp": _build_amp,
    "kimi": _build_kimi,
    "crush": _build_crush,
    "copilot": _build_copilot,
    "droid": _build_droid,
    "iflow": _build_iflow,
    "qwen": _build_qwen,
    "vibe": _build_vibe,
    "forge": _build_forge,
    "junie": _build_junie,
    "ccs": _build_ccs,
}

HARNESS_CONFIG_PATHS: dict[str, str] = {
    "opencode": "/app/.opencode.json",
    "crush": "/app/.opencode.json",
    "pi": "/root/.pi/agent/models.json",
}

HARNESS_USER: dict[str, str] = {
    "claude": "agent",
    "ccs": "agent",
}


def _get_harness_config() -> tuple[str, str, str, str]:
    """Read harness configuration from environment variables."""
    harness = os.environ.get("AGENT_HARNESS", "")
    model = os.environ.get("AGENT_MODEL", "")
    base_url = os.environ.get("LOCAL_BASE_URL", "")
    api_key = os.environ.get("LOCAL_API_KEY", "")
    return harness, model, base_url, api_key


@solver
def harness_solver(
    host_steps_dir: Path,
    test_timeout: int = 1200,
    agent_timeout: int = 3600,
    writable_patterns: list[str] | None = None,
) -> Solver:
    """Solver that runs an external agent harness instead of inspect-ai's generate loop.

    1. Inject visible files into /app/files/
    2. Run the agent harness CLI with the task prompt
    3. Capture stdout/stderr as a ChatMessageAssistant
    4. Inject hidden files and run pytest for scoring
    5. Remove hidden files
    """
    challenge_dir = host_steps_dir
    _writable = writable_patterns or []

    async def _run(cmd: str, timeout: int = 120) -> int:
        result = await sandbox().exec(["bash", "-lc", cmd], timeout=timeout)
        return result.returncode

    async def _write_reward(value: float) -> None:
        await sandbox().write_file(REWARD_FILE, f"{value:.6f}")

    async def _write_status(step_results: dict[int, bool]) -> None:
        lines = [
            f"stage{s}={'pass' if step_results.get(s, False) else 'fail'}"
            for s in [1]
        ]
        await sandbox().write_file(STATUS_FILE, "\n".join(lines) + "\n")

    async def _write_details(details: dict) -> None:
        await sandbox().write_file(DETAILS_FILE, json.dumps(details, indent=2))

    async def _inject_visible() -> None:
        files_dir = challenge_dir / "files"
        if not files_dir.exists():
            return
        container_root = "/app/files"
        await _run(f"mkdir -p {container_root}", timeout=10)
        for host_file in files_dir.rglob("*"):
            if not host_file.is_file():
                continue
            if "__pycache__" in host_file.parts or host_file.suffix == ".pyc":
                continue
            rel = host_file.relative_to(files_dir)
            target = f"{container_root}/{rel.as_posix()}"
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

        await _run(
            f"find {container_root} -type f -exec chmod a-w {{}} + 2>/dev/null; true",
            timeout=10,
        )
        for pattern in _writable:
            await _run(
                f"chmod a+w {container_root}/{pattern} 2>/dev/null; true",
                timeout=10,
            )

    async def _inject_hidden() -> None:
        hidden_dir = challenge_dir / "hidden"
        if not hidden_dir.exists():
            return
        await _remove_hidden()
        await _run("mkdir -p /app/hidden", timeout=10)
        for host_file in hidden_dir.rglob("*"):
            if not host_file.is_file():
                continue
            if "__pycache__" in host_file.parts or host_file.suffix == ".pyc":
                continue
            rel = host_file.relative_to(hidden_dir)
            target = f"/app/hidden/{rel.as_posix()}"
            parent_dir = str(Path(target).parent)
            if parent_dir != "/app/hidden":
                await _run(f"mkdir -p {parent_dir}", timeout=10)
            await sandbox().write_file(target, host_file.read_bytes())
        await _run(
            "find /app/hidden -type f -exec chmod a-w {} + 2>/dev/null; true",
            timeout=10,
        )

    async def _remove_hidden() -> None:
        await _run("rm -rf /app/hidden", timeout=120)

    async def _run_stage_tests(details: dict) -> tuple[bool, int, int]:
        step_key = "step1"
        gate_cmd = _stage_pytest_shell(
            test_files=[
                "/app/files/tests.py",
                "/app/hidden/hidden_tests.py",
            ],
            ctrf_path="/logs/verifier/ctrf.json",
        )
        details["steps"][step_key]["gate_command"] = gate_cmd

        await _inject_hidden()

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
            await _remove_hidden()

    async def solve(state, generate: Generate):
        step_results: dict[int, bool] = {}
        details: dict = {"steps": {"step1": {"gate_result": "not_run"}}}

        await _run("mkdir -p /logs/verifier", timeout=120)
        await _write_reward(0.0)
        await _write_status(step_results)
        await _write_details(details)

        await _inject_visible()

        harness_name, model, base_url, api_key = _get_harness_config()
        if harness_name not in HARNESSES:
            state.messages.append(
                ChatMessageAssistant(
                    content=f"[harness_eval] Unknown harness: {harness_name!r}. "
                    f"Available: {', '.join(HARNESSES.keys())}"
                )
            )
            state.completed = True
            return state

        prompt = state.input_text
        build_fn = HARNESSES[harness_name]
        cmd, env_vars, config_content = build_fn(prompt, model, base_url, api_key)

        if config_content is not None:
            config_path = HARNESS_CONFIG_PATHS.get(
                harness_name, f"/app/.{harness_name}.json"
            )
            parent = str(Path(config_path).parent)
            await _run(f"mkdir -p {parent}", timeout=10)
            await sandbox().write_file(config_path, config_content)

        details["steps"]["step1"]["harness"] = harness_name
        details["steps"]["step1"]["harness_cmd"] = shlex.join(cmd)
        await _write_details(details)

        run_user = HARNESS_USER.get(harness_name)
        if run_user:
            await _run(f"chown -R {run_user}:{run_user} /app", timeout=30)

        try:
            result = await sandbox().exec(
                cmd,
                env=env_vars,
                cwd="/app",
                user=run_user,
                timeout=agent_timeout,
            )
            stdout_text = result.stdout if isinstance(result.stdout, str) else str(result.stdout)
            stderr_text = result.stderr if isinstance(result.stderr, str) else str(result.stderr)
            exit_code = result.returncode
        except TimeoutError:
            stdout_text = ""
            stderr_text = f"[harness_eval] Agent harness timed out after {agent_timeout}s"
            exit_code = -1

        conversation = []
        if stdout_text.strip():
            conversation.append(f"=== {harness_name} stdout ===\n{stdout_text}")
        if stderr_text.strip():
            conversation.append(f"=== {harness_name} stderr ===\n{stderr_text}")
        conversation.append(f"=== exit code: {exit_code} ===")

        state.messages.append(
            ChatMessageAssistant(content="\n\n".join(conversation))
        )

        details["steps"]["step1"]["harness_exit_code"] = exit_code
        details["steps"]["step1"]["harness_stdout_len"] = len(stdout_text)
        details["steps"]["step1"]["harness_stderr_len"] = len(stderr_text)
        await _write_details(details)

        ok, passed_count, total_count = await _run_stage_tests(details)
        step_results[1] = ok

        if ok:
            reward = 1.0
        elif total_count > 0:
            reward = passed_count / total_count
        else:
            reward = 0.0

        await _write_reward(reward)
        await _write_status(step_results)

        state.completed = True
        return state

    return solve


@scorer(metrics=[accuracy(), stderr()])
def harness_scorer(
    reward_file: str = REWARD_FILE,
    status_file: str = STATUS_FILE,
    details_file: str = DETAILS_FILE,
) -> Scorer:
    """Reads reward/status/details written by harness_solver."""

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


def create_task(
    *,
    challenge_dir: Path,
    variant_names: str | list[str] | None = "default",
    test_timeout: int = 1200,
    agent_timeout: int = 3600,
    writable_patterns: list[str] | None = None,
) -> Task:
    """Build a harness-based eval task from a challenge directory."""
    challenge_dir = challenge_dir.resolve()
    challenges_root = challenge_dir.parent

    dataset = create_agentic_eval_dataset(
        root_dir=challenge_dir
    ).filter_by_metadata_field("variant_name", variant_names)
    dataset = dataset.flat_map(_convert_sandbox_for_local_build(challenges_root))

    return Task(
        dataset=dataset,
        solver=harness_solver(
            host_steps_dir=challenge_dir,
            test_timeout=test_timeout,
            agent_timeout=agent_timeout,
            writable_patterns=writable_patterns,
        ),
        scorer=harness_scorer(),
    )
