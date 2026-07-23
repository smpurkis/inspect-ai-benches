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

from common.reporting import build_report, load_trials


ROOT = Path(__file__).resolve().parent
DEFAULT_JOBS_DIR = ROOT / "jobs"


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
    command = [
        harbor,
        "run",
        "--path",
        str(ROOT),
        "--agent",
        "common.harbor_agent:GodBenchAgent",
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
    environment["OPENAI_BASE_URL"] = args.base_url
    environment["OPENAI_API_KEY"] = args.api_key
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT), environment.get("PYTHONPATH", "")) if part
    )
    return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=False)
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
