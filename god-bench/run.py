#!/usr/bin/env python3
"""Run native Harbor GOD-Bench jobs against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlsplit, urlunsplit

from common.reporting import build_report, load_trials


ROOT = Path(__file__).resolve().parent
DEFAULT_JOBS_DIR = ROOT / "jobs"
AGENTS = {
    "strict": "common.harbor_agent:GodBenchAgent",
    "pi": "common.harbor_cli_agents:GodBenchPi",
    "opencode": "common.harbor_cli_agents:GodBenchOpenCode",
}


def active_tasks() -> list[str]:
    return sorted(
        path.parent.name
        for path in ROOT.glob("*/task.toml")
        if path.parent.name not in {"archive", "common"}
    )


def _model_name(value: str) -> str:
    return value if "/" in value else f"openai/{value}"


def _job_name(model: str) -> str:
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"god-bench-{safe_model}-{stamp}"


def _container_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return value
    host = "172.17.0.1"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _prepare_cli_tasks(selected: list[str], destination: Path) -> None:
    for task in selected:
        target = destination / task
        shutil.copytree(ROOT / task, target)
        contract = tomllib.loads(
            (target / "files" / "contract.toml").read_text(encoding="utf-8")
        )
        wall_clock_seconds = int(contract["limits"]["wall_clock_seconds"])
        config_path = target / "task.toml"
        config = config_path.read_text(encoding="utf-8")
        config = re.sub(
            r"(?m)^timeout_sec = \d+(?:\.\d+)?$",
            f"timeout_sec = {wall_clock_seconds}.0",
            config,
            count=1,
        )
        config = config.replace(
            'network_mode = "no-network"', 'network_mode = "public"', 1
        )
        config = config.replace(
            "[verifier]\n", '[verifier]\nnetwork_mode = "no-network"\n', 1
        )
        config_path.write_text(config, encoding="utf-8")


def run_harbor(args: argparse.Namespace) -> int:
    harbor = shutil.which("harbor")
    if harbor is None:
        raise RuntimeError("Harbor is not installed; run `uv sync` in god-bench/")

    selected = [item.strip() for item in args.tasks.split(",") if item.strip()]
    available = active_tasks()
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ValueError(
            f"unknown task(s): {', '.join(unknown)}; available: {', '.join(available)}"
        )

    model = _model_name(args.model)
    temporary_tasks = None
    task_root = ROOT
    if args.agent != "strict":
        temporary_tasks = tempfile.TemporaryDirectory(prefix="god-bench-harbor-")
        task_root = Path(temporary_tasks.name)
        _prepare_cli_tasks(selected, task_root)

    command = [
        harbor,
        "run",
        "--path",
        str(task_root),
        "--agent",
        AGENTS[args.agent],
        "--model",
        model,
        "--verifier",
        "common.harbor_verifier:GodBenchVerifier",
        "--n-attempts",
        str(args.rounds),
        "--n-concurrent",
        str(args.parallel),
        "--jobs-dir",
        str(args.jobs_dir),
        "--job-name",
        args.job_name or _job_name(model),
        "--yes",
    ]
    for task in selected:
        command.extend(["--include-task-name", task])

    environment = os.environ.copy()
    agent_base_url = (
        args.base_url if args.agent == "strict" else _container_base_url(args.base_url)
    )
    environment["OPENAI_BASE_URL"] = agent_base_url
    environment["OPENAI_API_KEY"] = args.api_key
    if args.agent != "strict":
        command.extend(["--agent-env", f"OPENAI_BASE_URL={agent_base_url}"])
        command.extend(["--agent-env", f"OPENAI_API_KEY={args.api_key}"])
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT), environment.get("PYTHONPATH", "")) if part
    )
    try:
        return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode
    finally:
        if temporary_tasks is not None:
            temporary_tasks.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=False)
    parser.add_argument("--agent", choices=sorted(AGENTS), default="strict")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--tasks", default="")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--jobs-dir", type=Path, default=DEFAULT_JOBS_DIR)
    parser.add_argument("--job-name")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    if args.rounds < 1 or args.parallel < 1:
        parser.error("--rounds and --parallel must be positive")
    if not args.report_only:
        if not args.model:
            parser.error("--model is required")
        if not args.base_url or not args.api_key:
            parser.error("--base-url and --api-key are required")
        result = run_harbor(args)
        if result != 0:
            return result

    trials = load_trials(args.jobs_dir)
    if not trials:
        print(f"No Harbor trial results found under {args.jobs_dir}")
        return 0
    report = build_report(trials)
    print(report)
    args.jobs_dir.mkdir(parents=True, exist_ok=True)
    (args.jobs_dir / "god-bench-report.txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
