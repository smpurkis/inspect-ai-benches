#!/usr/bin/env python3
"""Run all 13 tasks × 2 models × N rounds, max 20 parallel at a time.

Combines any existing round-1 data from logs/full_bench/ with new rounds,
then reports per-task averages, avg-of-max, and a final score.

Usage:
    uv run python run_multi_bench.py              # run 4 new rounds + retry cifar10 gpt-5.4
    uv run python run_multi_bench.py --report-only
    uv run python run_multi_bench.py --new-rounds 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT      = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "closed-terminal-bench"

# Existing round-1 data (may have some errors)
OLD_LOGS  = ROOT / "logs" / "full_bench"
# New rounds go here
NEW_LOGS  = ROOT / "logs" / "multi_bench"

LOCAL_BASE_URL = "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/"
LOCAL_API_KEY  = "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk"

MAX_PARALLEL = 20

MODELS = ["gpt-5", "gpt-5.4", "gpt-4.1-mini", "gpt-4o-global"]

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

TASK_TIMEOUTS: dict[str, int] = {
    "cifar10-burn-optimise":                    3600,   # bumped from 1800 — gpt-5.4 took 32m
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
                for entry in data.get("results", {}).get("scores", []):
                    for mname, mdata in entry.get("metrics", {}).items():
                        if mname in ("accuracy", "mean"):
                            val = mdata.get("value")
                            if val is not None:
                                try:
                                    return float(val)
                                except (ValueError, TypeError):
                                    pass
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Single eval runner
# ---------------------------------------------------------------------------

def run_eval(model: str, task: str, round_num: int) -> dict:
    log_dir   = NEW_LOGS / model / task / f"round_{round_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)
    timeout   = TASK_TIMEOUTS.get(task, 3600)
    task_spec = f"closed-terminal-bench/{task}/run.py@run"

    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", f"openai-api/local/{model}",
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--max-tasks", "1",
        "--display", "none",
    ]

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(ROOT), timeout=timeout + 300,
        )
        elapsed = time.time() - t0
        rc = proc.returncode
        stderr_tail = proc.stderr[-300:] if proc.stderr and rc != 0 else ""
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        rc = -1
        stderr_tail = f"TIMEOUT after {elapsed:.0f}s"

    eval_files = sorted(log_dir.glob("*.eval"))
    score = parse_score(eval_files[0]) if eval_files else None

    status = "ok" if rc == 0 else f"FAIL(rc={rc})"
    score_s = f"{score:.4f}" if score is not None else "  n/a"
    short = TASK_SHORT.get(task, task)
    print(
        f"  ✅ r{round_num:02d} {model:<10} {short:<22} score={score_s}  {elapsed/60:.1f}m  [{status}]",
        flush=True,
    )
    if stderr_tail and rc != 0:
        print(f"       stderr: {stderr_tail[:150]}", flush=True)

    sidecar = log_dir / "_timing.json"
    sidecar.write_text(json.dumps({
        "model": model, "task": task, "round": round_num,
        "elapsed": elapsed, "rc": rc, "score": score,
    }))

    return {"model": model, "task": task, "round": round_num,
            "score": score, "elapsed": elapsed, "rc": rc}


# ---------------------------------------------------------------------------
# Load all results (old round-1 + new rounds)
# ---------------------------------------------------------------------------

def load_all_results() -> list[dict]:
    results: list[dict] = []

    # Old round-1 from full_bench (skip errors)
    for model in MODELS:
        for task in ALL_TASKS:
            sidecar = OLD_LOGS / model / task / "_timing.json"
            if sidecar.exists():
                try:
                    d = json.loads(sidecar.read_text())
                    if d.get("rc") == 0 and d.get("score") is not None:
                        d["round"] = 1
                        results.append(d)
                except Exception:
                    pass

    # New rounds from multi_bench
    for sidecar in sorted(NEW_LOGS.rglob("_timing.json")):
        try:
            d = json.loads(sidecar.read_text())
            if d.get("score") is not None:
                results.append(d)
        except Exception:
            pass

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(results: list[dict], tasks: list[str], models: list[str]) -> str:
    # Group scores: scores[(model, task)] = [score, ...]
    scores: dict[tuple[str, str], list[float]] = {}
    for r in results:
        k = (r["model"], r["task"])
        if r.get("score") is not None:
            scores.setdefault(k, []).append(r["score"])

    task_w = 24
    col_w  = 16   # wide enough for "avg(n) / max"

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("  MULTI-ROUND BENCH — avg score per task  (format: avg[n] / max)")
    lines.append("=" * 80)
    lines.append("")

    # Header
    hdr = f"{'Task':<{task_w}}"
    for m in models:
        hdr += f"  {m:^{col_w}}"
    lines.append(hdr)
    lines.append("-" * (task_w + len(models) * (col_w + 2)))

    model_avgs: dict[str, list[float]] = {m: [] for m in models}
    model_maxs: dict[str, list[float]] = {m: [] for m in models}

    for task in tasks:
        short = TASK_SHORT.get(task, task)
        row = f"{short:<{task_w}}"
        for m in models:
            ss = scores.get((m, task), [])
            if ss:
                avg = sum(ss) / len(ss)
                mx  = max(ss)
                cell = f"{avg:.4f}[{len(ss)}]/{mx:.4f}"
                model_avgs[m].append(avg)
                model_maxs[m].append(mx)
            else:
                cell = "   err/missing  "
            row += f"  {cell:^{col_w}}"
        lines.append(row)

    lines.append("-" * (task_w + len(models) * (col_w + 2)))

    # Summary rows
    avg_row    = f"{'AVG of avgs':<{task_w}}"
    avgmax_row = f"{'AVG of max scores':<{task_w}}"
    n_row      = f"{'Tasks scored':<{task_w}}"

    for m in models:
        avgs = model_avgs[m]
        maxs = model_maxs[m]
        avg_of_avgs = sum(avgs) / len(avgs) if avgs else 0.0
        avg_of_maxs = sum(maxs) / len(maxs) if maxs else 0.0
        avg_row    += f"  {f'{avg_of_avgs:.4f}':^{col_w}}"
        avgmax_row += f"  {f'{avg_of_maxs:.4f}':^{col_w}}"
        n_row      += f"  {f'{len(avgs)}/{len(tasks)}':^{col_w}}"

    lines.append(avg_row)
    lines.append(avgmax_row)
    lines.append(n_row)
    lines.append("")

    # Model summary
    lines.append("=" * 80)
    lines.append("  MODEL SUMMARY")
    lines.append("=" * 80)
    for m in models:
        avgs = model_avgs[m]
        maxs = model_maxs[m]
        n    = len(avgs)
        avg_of_avgs = sum(avgs) / len(avgs) if avgs else 0.0
        avg_of_maxs = sum(maxs) / len(maxs) if maxs else 0.0

        # Per-task run counts
        run_counts = [len(scores.get((m, t), [])) for t in tasks]
        total_runs = sum(run_counts)

        lines.append(f"  {m:<12}")
        lines.append(f"    Tasks scored  : {n}/{len(tasks)}")
        lines.append(f"    Avg of avgs   : {avg_of_avgs:.4f}")
        lines.append(f"    Avg of maxes  : {avg_of_maxs:.4f}  ← 'best possible' score")
        lines.append(f"    Total runs    : {total_runs}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--new-rounds", type=int, default=4,
                        help="How many new rounds to run (default: 4)")
    parser.add_argument("--models", default="",
                        help="Comma-separated models to run, e.g. gpt-4.1-mini,gpt-4o-global")
    args = parser.parse_args()

    sel_models = [m.strip() for m in args.models.split(",") if m.strip()] or MODELS

    if not args.report_only:
        NEW_LOGS.mkdir(parents=True, exist_ok=True)

        # Build job list
        jobs: list[tuple[str, str, int]] = []
        for rnd in range(1, args.new_rounds + 1):
            for model in sel_models:
                for task in ALL_TASKS:
                    jobs.append((model, task, rnd))

        total = len(jobs)
        print(f"\n🚀 {total} evals queued  ({MAX_PARALLEL} max parallel)")
        print(f"   Models : {', '.join(sel_models)}")
        print(f"   Rounds : {args.new_rounds} × {len(ALL_TASKS)} tasks\n")
        print(f"  {'Rnd':<4} {'Model':<10} {'Task':<22}  Result")
        print(f"  {'-'*4} {'-'*10} {'-'*22}  {'-'*30}")

        completed = 0
        wall_start = time.time()

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            futures = {
                pool.submit(run_eval, model, task, rnd): (model, task, rnd)
                for model, task, rnd in jobs
            }
            for fut in as_completed(futures):
                model, task, rnd = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    print(f"  ❌ r{rnd:02d} {model} / {task}: {e}", flush=True)
                completed += 1
                print(f"  [{completed}/{total} done]", flush=True)

        wall = time.time() - wall_start
        print(f"\n  All {total} evals done in {wall/60:.1f} min wall time\n")

    # Generate report
    results = load_all_results()
    print(f"  Loaded {len(results)} valid scored runs from all rounds\n")

    report = build_report(results, ALL_TASKS, sel_models)
    print(report)

    out = NEW_LOGS / "report.txt"
    out.write_text(report)
    print(f"  Report saved → {out}")

    raw = NEW_LOGS / "results.json"
    raw.write_text(json.dumps(results, indent=2, default=str))
    print(f"  Raw JSON  → {raw}")


if __name__ == "__main__":
    main()
