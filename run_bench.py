#!/usr/bin/env python3
"""Run all 5 closed-terminal-bench tasks and report results with statistics.

Usage:
    uv run python run_bench.py                          # 5 runs, 3 parallel
    uv run python run_bench.py --runs 3 --parallel 2
    uv run python run_bench.py --report-only             # parse existing logs
    uv run python run_bench.py --report-only --log-dir logs/v2_5x
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "closed-terminal-bench"

TASKS = [
    "cifar10-burn-optimise",
    "pandas-to-polars",
    "git-leak-recovery-and-sanitize",
    "rust-python-linear-algebra-extension",
    "wasm-compression-stepwise",
]

MODEL = os.environ.get("MODEL", "openai-api/local/gpt-5")
LOCAL_BASE_URL = os.environ.get(
    "LOCAL_BASE_URL",
    "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/",
)
LOCAL_API_KEY = os.environ.get(
    "LOCAL_API_KEY",
    "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk",
)


def run_single_task(task: str, run_num: int, log_base: Path) -> tuple[str, int, float | None]:
    """Run a single task once. Returns (task, run_num, score)."""
    log_dir = log_base / f"{task}_run{run_num}"
    log_dir.mkdir(parents=True, exist_ok=True)

    task_spec = f"closed-terminal-bench/{task}/run.py@run"
    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", MODEL,
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--display", "none",
    ]

    print(f"[{task} #{run_num}] Starting...", flush=True)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=3600,
        )
    except subprocess.TimeoutExpired:
        print(f"[{task} #{run_num}] TIMEOUT (60min)", flush=True)
        return task, run_num, None

    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-500:]
        print(f"[{task} #{run_num}] FAILED (rc={result.returncode}): {stderr_tail}", flush=True)
    else:
        print(f"[{task} #{run_num}] Complete", flush=True)

    # Parse the result immediately
    score = None
    for eval_file in sorted(log_dir.glob("*.eval")):
        score = extract_score(eval_file)
        if score is not None:
            break

    if score is not None:
        print(f"[{task} #{run_num}] Score: {score:.3f}", flush=True)
    else:
        print(f"[{task} #{run_num}] No score extracted", flush=True)

    return task, run_num, score


def extract_score(eval_path: Path) -> float | None:
    """Extract staged_scorer value from an Inspect v2 .eval ZIP."""
    try:
        with zipfile.ZipFile(eval_path, "r") as zf:
            # Primary: summaries.json has task name + score
            if "summaries.json" in zf.namelist():
                with zf.open("summaries.json") as f:
                    summaries = json.load(f)
                for entry in summaries:
                    val = entry.get("scores", {}).get("staged_scorer", {}).get("value")
                    if val is not None:
                        return float(val)

            # Fallback: reductions.json
            if "reductions.json" in zf.namelist():
                with zf.open("reductions.json") as f:
                    reductions = json.load(f)
                for r in reductions:
                    if r.get("scorer") == "staged_scorer":
                        for sample in r.get("samples", []):
                            val = sample.get("value")
                            if val is not None:
                                return float(val)
    except Exception as e:
        print(f"  Warning: parse error for {eval_path.name}: {e}", flush=True)
    return None


def extract_task_name(eval_path: Path) -> str | None:
    """Get the eval_name from an .eval ZIP."""
    try:
        with zipfile.ZipFile(eval_path, "r") as zf:
            if "summaries.json" in zf.namelist():
                with zf.open("summaries.json") as f:
                    summaries = json.load(f)
                for entry in summaries:
                    name = entry.get("metadata", {}).get("eval_name")
                    if name:
                        return name
    except Exception:
        pass
    return None


def collect_results(log_dir: Path) -> dict[str, list[float]]:
    """Collect results from log directories."""
    results = defaultdict(list)

    # Per-task run directories (new format)
    for task in TASKS:
        for run_dir in sorted(log_dir.glob(f"{task}_run*")):
            for eval_file in sorted(run_dir.glob("*.eval")):
                score = extract_score(eval_file)
                if score is not None:
                    results[task].append(score)

    # Round directories (legacy format)
    if not results:
        for round_dir in sorted(log_dir.glob("round_*")):
            for eval_file in sorted(round_dir.glob("*.eval")):
                task_name = extract_task_name(eval_file)
                score = extract_score(eval_file)
                if task_name and score is not None:
                    results[task_name].append(score)

    return dict(results)


def report(results: dict[str, list[float]]) -> str:
    """Print and return results table with min, max, avg, std per task."""
    lines = []

    def p(s=""):
        print(s, flush=True)
        lines.append(s)

    p()
    p("=" * 95)
    p("BENCHMARK RESULTS")
    p("=" * 95)
    p(f"{'Task':<42} {'Runs':>4}  {'Avg':>6}  {'Std':>6}  {'Min':>6}  {'Max':>6}  Scores")
    p("-" * 95)

    all_means = []
    for task in TASKS:
        scores = results.get(task, [])
        if scores:
            avg = statistics.mean(scores)
            std = statistics.stdev(scores) if len(scores) >= 2 else 0.0
            mn = min(scores)
            mx = max(scores)
            all_means.append(avg)
            scores_str = " ".join(f"{s:.3f}" for s in scores)
            flag = " !!" if std >= 0.1 else ""
            p(f"{task:<42} {len(scores):>4}  {avg:>6.3f}  {std:>6.3f}  {mn:>6.3f}  {mx:>6.3f}  {scores_str}{flag}")
        else:
            p(f"{task:<42}    -       -       -       -       -  (no results)")

    p("-" * 95)
    if all_means:
        overall = statistics.mean(all_means)
        p(f"{'Overall mean':<42}        {overall:>6.3f}")
    p("=" * 95)

    p()
    any_high = False
    for task in TASKS:
        scores = results.get(task, [])
        if len(scores) >= 2:
            std = statistics.stdev(scores)
            if std >= 0.1:
                if not any_high:
                    p("!! HIGH VARIANCE (std >= 0.1):")
                    any_high = True
                p(f"  {task}: std={std:.3f} scores={scores}")
    if not any_high:
        p("All tasks have std < 0.1")
    p()

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run closed-terminal-bench")
    parser.add_argument("--runs", type=int, default=5, help="Runs per task (default: 5)")
    parser.add_argument("--parallel", type=int, default=3, help="Max parallel runs (default: 3)")
    parser.add_argument("--log-dir", type=str, default=None, help="Log directory (default: logs/run_<timestamp>)")
    parser.add_argument("--report-only", action="store_true", help="Just report existing results")
    args = parser.parse_args()

    if args.report_only:
        log_dir = Path(args.log_dir) if args.log_dir else ROOT / "logs"
        if not log_dir.is_absolute():
            log_dir = ROOT / log_dir
        results = collect_results(log_dir)
        report(results)
        return

    if args.log_dir:
        log_dir = Path(args.log_dir)
        if not log_dir.is_absolute():
            log_dir = ROOT / log_dir
    else:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = ROOT / "logs" / f"run_{ts}"

    log_dir.mkdir(parents=True, exist_ok=True)

    # Build job queue: tasks * runs
    jobs = [(task, run_num) for run_num in range(1, args.runs + 1) for task in TASKS]
    total = len(jobs)
    completed_count = 0
    live_scores: dict[str, list[float]] = defaultdict(list)

    print(f"Log dir:  {log_dir}")
    print(f"Model:    {MODEL}")
    print(f"Jobs:     {total} ({len(TASKS)} tasks x {args.runs} runs)")
    print(f"Parallel: {args.parallel}")
    print(flush=True)

    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {
            executor.submit(run_single_task, task, run_num, log_dir): (task, run_num)
            for task, run_num in jobs
        }
        for future in as_completed(futures):
            task, run_num = futures[future]
            completed_count += 1
            try:
                _, _, score = future.result()
                if score is not None:
                    live_scores[task].append(score)
            except Exception as e:
                print(f"[{task} #{run_num}] Error: {e}", flush=True)
            print(f"--- Progress: {completed_count}/{total} ---", flush=True)

    # Final report from disk (authoritative)
    results = collect_results(log_dir)
    report(results)


if __name__ == "__main__":
    main()
