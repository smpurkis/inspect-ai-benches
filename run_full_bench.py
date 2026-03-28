#!/usr/bin/env python3
"""Run all 13 closed-terminal-bench tasks × 2 models (gpt-5, gpt-5.4) fully in parallel.

Launches up to 26 concurrent evals, prints a status line as each completes,
then prints a per-model × per-task results table with totals and averages.

Usage:
    uv run python run_full_bench.py
    uv run python run_full_bench.py --report-only
    uv run python run_full_bench.py --models gpt-5           # single model
    uv run python run_full_bench.py --tasks cifar10-burn-optimise,pandas-to-polars
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

ROOT      = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "closed-terminal-bench"
LOGS_BASE = ROOT / "logs" / "full_bench"

LOCAL_BASE_URL = "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/"
LOCAL_API_KEY  = "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELS = [
    "gpt-5",
    "gpt-5.4",
]

# All 13 tasks (directories with run.py + compose.yaml)
ALL_TASKS: list[str] = [
    "cifar10-burn-optimise",
    "distributed-log-reconstruction-stepwise",
    "ext4-recovery-stepwise",
    "git-leak-recovery-and-sanitize",
    "nim-bytecode-vm-stepwise",
    "pandas-to-polars",
    "physics-simulation-stepwise",
    "pokemon-sapphire-episode",
    "rust-python-linear-algebra-extension",
    "samscript-interpreter",
    "sql-migration-rebuild-stepwise",
    "text-pokemon-battle-engine",
    "wasm-compression-stepwise",
]

# Per-task timeouts (seconds) — generous for slower tasks
TASK_TIMEOUTS: dict[str, int] = {
    "cifar10-burn-optimise":                    1800,
    "distributed-log-reconstruction-stepwise":  3600,
    "ext4-recovery-stepwise":                   3600,
    "git-leak-recovery-and-sanitize":           3600,
    "nim-bytecode-vm-stepwise":                 3600,
    "pandas-to-polars":                         1800,
    "physics-simulation-stepwise":              3600,
    "pokemon-sapphire-episode":                 3600,
    "rust-python-linear-algebra-extension":     1800,
    "samscript-interpreter":                    3600,
    "sql-migration-rebuild-stepwise":           3600,
    "text-pokemon-battle-engine":               3600,
    "wasm-compression-stepwise":                3600,
}

# Short display names (≤30 chars)
TASK_SHORT: dict[str, str] = {
    "cifar10-burn-optimise":                    "cifar10-burn",
    "distributed-log-reconstruction-stepwise":  "distrib-log-recon",
    "ext4-recovery-stepwise":                   "ext4-recovery",
    "git-leak-recovery-and-sanitize":           "git-leak-sanitize",
    "nim-bytecode-vm-stepwise":                 "nim-bytecode-vm",
    "pandas-to-polars":                         "pandas-to-polars",
    "physics-simulation-stepwise":              "physics-sim",
    "pokemon-sapphire-episode":                 "pokemon-sapphire",
    "rust-python-linear-algebra-extension":     "rust-py-linalg",
    "samscript-interpreter":                    "samscript",
    "sql-migration-rebuild-stepwise":           "sql-migration",
    "text-pokemon-battle-engine":               "text-pokemon",
    "wasm-compression-stepwise":                "wasm-compress",
}

# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------

def parse_score(eval_path: Path) -> float | None:
    try:
        with zipfile.ZipFile(eval_path, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    data = json.loads(zf.read(name))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for score_entry in data.get("results", {}).get("scores", []):
                    for mname, mdata in score_entry.get("metrics", {}).items():
                        if mname in ("accuracy", "mean"):
                            val = mdata.get("value")
                            if val is not None:
                                try:
                                    return float(val)
                                except (ValueError, TypeError):
                                    pass
    except (zipfile.BadZipFile, Exception):
        return None
    return None


# ---------------------------------------------------------------------------
# Single eval runner
# ---------------------------------------------------------------------------

def run_eval(model: str, task: str) -> dict:
    model_id   = f"openai-api/local/{model}"
    log_dir    = LOGS_BASE / model / task
    log_dir.mkdir(parents=True, exist_ok=True)
    timeout    = TASK_TIMEOUTS.get(task, 3600)
    task_spec  = f"closed-terminal-bench/{task}/run.py@run"

    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", model_id,
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--max-tasks", "1",
        "--display", "none",
    ]

    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(ROOT), timeout=timeout + 120,
        )
        elapsed = time.time() - t0
        rc = result.returncode
        stderr_tail = result.stderr[-400:] if result.stderr and rc != 0 else ""
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        rc = -1
        stderr_tail = f"TIMEOUT after {elapsed:.0f}s"

    # Parse score from eval file
    eval_files = sorted(log_dir.glob("*.eval"))
    score = parse_score(eval_files[0]) if eval_files else None

    status = "ok" if rc == 0 else f"fail(rc={rc})"
    score_s = f"{score:.4f}" if score is not None else " n/a "

    print(
        f"  ✅ {model:<10} | {TASK_SHORT.get(task, task):<22} | "
        f"score={score_s}  time={elapsed/60:.1f}m  [{status}]",
        flush=True,
    )
    if stderr_tail:
        print(f"     STDERR: {stderr_tail[:200]}", flush=True)

    # Save sidecar
    sidecar = log_dir / "_timing.json"
    sidecar.write_text(json.dumps({
        "model": model, "task": task,
        "elapsed": elapsed, "rc": rc, "score": score,
    }))

    return {"model": model, "task": task, "score": score, "elapsed": elapsed, "rc": rc}


# ---------------------------------------------------------------------------
# Report table
# ---------------------------------------------------------------------------

def build_report(results: list[dict], tasks: list[str], models: list[str]) -> str:
    # Index: results[(model, task)] = {score, elapsed, rc}
    idx: dict[tuple[str, str], dict] = {}
    for r in results:
        idx[(r["model"], r["task"])] = r

    col_w = 10  # per-model column width
    task_w = 24

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("  FULL BENCH RESULTS  —  all tasks × all models")
    lines.append("=" * 80)
    lines.append("")

    # Header row
    header = f"{'Task':<{task_w}}"
    for m in models:
        header += f"  {m[:col_w]:>{col_w}}"
    lines.append(header)
    lines.append("-" * (task_w + len(models) * (col_w + 2)))

    # Per-task rows
    model_totals  = {m: [] for m in models}
    for task in tasks:
        short = TASK_SHORT.get(task, task)
        row = f"{short:<{task_w}}"
        for m in models:
            r = idx.get((m, task))
            if r and r["score"] is not None:
                s = f"{r['score']:.4f}"
                model_totals[m].append(r["score"])
            elif r:
                s = "err"
            else:
                s = "---"
            row += f"  {s:>{col_w}}"
        lines.append(row)

    lines.append("-" * (task_w + len(models) * (col_w + 2)))

    # Totals / averages
    avg_row   = f"{'AVG score':<{task_w}}"
    total_row = f"{'TOTAL tasks scored':<{task_w}}"
    time_row  = f"{'Wall time (min)':<{task_w}}"

    for m in models:
        scores = model_totals[m]
        avg  = sum(scores) / len(scores) if scores else 0.0
        avg_row   += f"  {f'{avg:.4f}':>{col_w}}"
        total_row += f"  {len(scores):>{col_w}}"

        # wall time = max elapsed (parallel so dominated by slowest)
        times = [idx[(m, t)]["elapsed"] for t in tasks if (m, t) in idx]
        wall = max(times) / 60 if times else 0.0
        time_row += f"  {f'{wall:.1f}m':>{col_w}}"

    lines.append(avg_row)
    lines.append(total_row)
    lines.append(time_row)
    lines.append("")

    # Per-model summary
    lines.append("=" * 80)
    lines.append("  MODEL SUMMARY")
    lines.append("=" * 80)
    for m in models:
        scores = model_totals[m]
        avg = sum(scores) / len(scores) if scores else 0.0
        n   = len(scores)
        lines.append(f"  {m:<14}  avg={avg:.4f}  tasks_scored={n}/{len(tasks)}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--models", default="", help="Comma-separated model names")
    parser.add_argument("--tasks",  default="", help="Comma-separated task names")
    args = parser.parse_args()

    sel_models = [m.strip() for m in args.models.split(",") if m.strip()] or MODELS
    sel_tasks  = [t.strip() for t in args.tasks.split(",")  if t.strip()] or ALL_TASKS

    total_jobs = len(sel_models) * len(sel_tasks)

    if not args.report_only:
        LOGS_BASE.mkdir(parents=True, exist_ok=True)
        print(f"\n🚀 Launching {total_jobs} evals in parallel")
        print(f"   Models : {', '.join(sel_models)}")
        print(f"   Tasks  : {len(sel_tasks)} tasks")
        print(f"   Workers: {total_jobs} (one per eval)\n")
        print(f"  {'Model':<10} | {'Task':<22} | {'Result'}")
        print(f"  {'-'*10}-+-{'-'*22}-+-{'-'*30}")

        results: list[dict] = []
        wall_start = time.time()

        with ThreadPoolExecutor(max_workers=total_jobs) as pool:
            futures = {
                pool.submit(run_eval, model, task): (model, task)
                for model in sel_models
                for task in sel_tasks
            }
            for fut in as_completed(futures):
                model, task = futures[fut]
                try:
                    results.append(fut.result())
                except Exception as e:
                    print(f"  ❌ {model} / {task}: EXCEPTION {e}", flush=True)
                    results.append({"model": model, "task": task, "score": None, "elapsed": None, "rc": -99})

        wall_elapsed = time.time() - wall_start
        print(f"\n  All {total_jobs} evals done in {wall_elapsed/60:.1f} minutes wall time\n")

        # Save raw results
        out_json = LOGS_BASE / "results.json"
        out_json.write_text(json.dumps(results, indent=2, default=str))
        print(f"  Raw results → {out_json}")

    else:
        # Load from sidecar files
        results = []
        for model in sel_models:
            for task in sel_tasks:
                sidecar = LOGS_BASE / model / task / "_timing.json"
                if sidecar.exists():
                    try:
                        results.append(json.loads(sidecar.read_text()))
                    except Exception:
                        pass

    report = build_report(results, sel_tasks, sel_models)
    print(report)

    out_txt = LOGS_BASE / "report.txt"
    out_txt.write_text(report)
    print(f"  Report → {out_txt}\n")


if __name__ == "__main__":
    main()
