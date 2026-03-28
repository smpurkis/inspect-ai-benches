#!/usr/bin/env python3
"""
Run gpt-oss-120b-low sequentially across all 13 tasks × 5 rounds.
Sequential (one at a time) to avoid OOM on local GPU.
"""
from __future__ import annotations

import json
import subprocess
import time
import zipfile
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
NEW_LOGS = ROOT / "logs" / "multi_bench"

LOCAL_BASE_URL = "http://localhost:8234/v1"
LOCAL_API_KEY  = "purkis-home-blah"
MODEL          = "gpt-oss-120b-Derestricted.MXFP4_MOE-low"
MODEL_SLUG     = "oss-120b-low"   # used for log dir name
ROUNDS         = 5

TASK_TIMEOUTS: dict[str, int] = {
    "cifar10-burn-optimise":                    3600,
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

ALL_TASKS = list(TASK_TIMEOUTS.keys())


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


def run_eval(task: str, round_num: int) -> dict:
    log_dir   = NEW_LOGS / MODEL_SLUG / task / f"round_{round_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)
    timeout   = TASK_TIMEOUTS.get(task, 3600)
    task_spec = f"closed-terminal-bench/{task}/run.py@run"
    short     = TASK_SHORT.get(task, task)

    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", f"openai-api/local/{MODEL}",
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--max-tasks", "1",
        "--display", "none",
    ]

    print(f"  ▶  r{round_num:02d} {short:<22}", end="", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(ROOT), timeout=timeout + 300,
        )
        elapsed = time.time() - t0
        rc = proc.returncode
        stderr_tail = proc.stderr[-200:] if proc.stderr and rc != 0 else ""
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        rc = -1
        stderr_tail = f"TIMEOUT after {elapsed:.0f}s"

    eval_files = sorted(log_dir.glob("*.eval"))
    score = parse_score(eval_files[0]) if eval_files else None

    status  = "ok" if rc == 0 else f"FAIL(rc={rc})"
    score_s = f"{score:.4f}" if score is not None else "  n/a"
    print(f"  score={score_s}  {elapsed/60:.1f}m  [{status}]", flush=True)
    if stderr_tail and rc != 0:
        print(f"       stderr: {stderr_tail[:150]}", flush=True)

    sidecar = log_dir / "_timing.json"
    sidecar.write_text(json.dumps({
        "model": MODEL_SLUG, "task": task, "round": round_num,
        "elapsed": elapsed, "rc": rc, "score": score,
    }))

    return {"task": task, "round": round_num, "score": score,
            "elapsed": elapsed, "rc": rc}


def main() -> None:
    total = len(ALL_TASKS) * ROUNDS
    print(f"\n🚀 {MODEL_SLUG}  —  {total} evals  ({len(ALL_TASKS)} tasks × {ROUNDS} rounds, sequential)")
    print(f"   Base URL : {LOCAL_BASE_URL}")
    print(f"   Model    : {MODEL}\n")

    wall_start = time.time()
    results = []
    done = 0

    for rnd in range(1, ROUNDS + 1):
        print(f"\n── Round {rnd}/{ROUNDS} ──────────────────────────────────")
        for task in ALL_TASKS:
            r = run_eval(task, rnd)
            results.append(r)
            done += 1
            print(f"  [{done}/{total} done]", flush=True)

    wall = time.time() - wall_start
    print(f"\n  All {total} evals done in {wall/60:.1f} min wall time\n")

    # Summary
    from collections import defaultdict
    import statistics
    task_scores: dict[str, list[float]] = defaultdict(list)
    for r in results:
        if r["score"] is not None:
            task_scores[r["task"]].append(r["score"])

    print(f"\n{'Task':<24} {'avg':>8}  {'max':>8}  {'n':>4}")
    print("-" * 50)
    avgs, maxes = [], []
    for task in ALL_TASKS:
        sc = task_scores[task]
        short = TASK_SHORT[task]
        if sc:
            avg = statistics.mean(sc)
            mx  = max(sc)
            avgs.append(avg)
            maxes.append(mx)
            print(f"{short:<24} {avg:>8.4f}  {mx:>8.4f}  {len(sc):>4}")
        else:
            print(f"{short:<24} {'—':>8}  {'—':>8}  {0:>4}")
    print("-" * 50)
    if avgs:
        print(f"{'avg-of-avgs':<24} {statistics.mean(avgs):>8.4f}")
        print(f"{'avg-of-max':<24} {statistics.mean(maxes):>8.4f}")


if __name__ == "__main__":
    main()
