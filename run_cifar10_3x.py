#!/usr/bin/env python3
"""Run cifar10-burn-optimise 3 times against GPT-5 and report results.

Usage:
    uv run python run_cifar10_3x.py
    uv run python run_cifar10_3x.py --report-only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "closed-terminal-bench"
LOGS_DIR = ROOT / "logs" / "cifar10_3x"

TASK = "cifar10-burn-optimise"
ROUNDS = 3

MODEL = os.environ.get("MODEL", "openai-api/local/gpt-5.2")
LOCAL_BASE_URL = os.environ.get(
    "LOCAL_BASE_URL",
    "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/",
)
LOCAL_API_KEY = os.environ.get(
    "LOCAL_API_KEY",
    "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk",
)


def docker_prune() -> None:
    result = subprocess.run(
        ["docker", "network", "prune", "-f"], capture_output=True, text=True
    )
    print(f"[docker] network prune: {result.stdout.strip() or '(no output)'}", flush=True)


def run_job(run_num: int) -> tuple[int, Path, float]:
    log_dir = LOGS_DIR / f"run_{run_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    task_spec = f"closed-terminal-bench/{TASK}/run.py@run"
    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", MODEL,
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--max-tasks", "1",
        "--display", "none",
    ]

    print(f"[cifar10 run={run_num}] Starting...", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    elapsed = time.time() - t0

    if result.returncode != 0:
        tail = result.stderr[-800:] if result.stderr else "(no stderr)"
        print(f"[cifar10 run={run_num}] FAILED (rc={result.returncode}) in {elapsed:.0f}s:\n{tail}", flush=True)
    else:
        print(f"[cifar10 run={run_num}] Done in {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)

    return run_num, log_dir, elapsed


def parse_eval_file(eval_path: Path) -> float | None:
    """Iterate all JSON entries in the zip to find the one with results.scores."""
    try:
        with zipfile.ZipFile(eval_path, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    data = json.loads(zf.read(name))
                except (json.JSONDecodeError, Exception):
                    continue
                if not isinstance(data, dict):
                    continue
                # Top-level results.scores[*].metrics.mean/accuracy
                for score_entry in data.get("results", {}).get("scores", []):
                    for mname, mdata in score_entry.get("metrics", {}).items():
                        if mname in ("accuracy", "mean"):
                            val = mdata.get("value")
                            if val is not None:
                                try:
                                    return float(val)
                                except (ValueError, TypeError):
                                    pass
                # Per-sample scores fallback
                for sample in data.get("samples", []):
                    for _scorer, scorer_data in sample.get("scores", {}).items():
                        val = scorer_data.get("value")
                        if val is not None:
                            try:
                                return float(val)
                            except (ValueError, TypeError):
                                pass
    except zipfile.BadZipFile:
        return None
    return None


def collect_results() -> list[float | None]:
    scores = []
    for run_num in range(1, ROUNDS + 1):
        run_dir = LOGS_DIR / f"run_{run_num:02d}"
        for eval_file in sorted(run_dir.glob("*.eval")):
            score = parse_eval_file(eval_file)
            scores.append(score)
            break
        else:
            scores.append(None)
    return scores


def report(scores: list[float | None], elapsed_times: list[float] | None = None) -> None:
    print()
    print("=" * 60)
    print(f"cifar10-burn-optimise  x{ROUNDS}  (GPT-5 / gpt-5.2)")
    print("=" * 60)
    valid = [s for s in scores if s is not None]
    for i, score in enumerate(scores, 1):
        time_str = ""
        if elapsed_times and i <= len(elapsed_times):
            t = elapsed_times[i - 1]
            time_str = f"  ({t/60:.1f}m)"
        score_str = f"{score:.4f}" if score is not None else "(no result)"
        print(f"  Run {i}: {score_str}{time_str}")
    print("-" * 60)
    if valid:
        mean = sum(valid) / len(valid)
        print(f"  Mean:  {mean:.4f}  (N={len(valid)})")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    if args.report_only:
        report(collect_results())
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    elapsed_times: list[float] = []
    print(f"Running cifar10-burn-optimise x{ROUNDS} sequentially\n")

    for run_num in range(1, ROUNDS + 1):
        # prune subnets between runs to avoid exhaustion
        if run_num > 1:
            docker_prune()
        _, _, elapsed = run_job(run_num)
        elapsed_times.append(elapsed)

    print("\nAll runs complete.")
    docker_prune()  # cleanup after

    scores = collect_results()
    report(scores, elapsed_times)


if __name__ == "__main__":
    main()
