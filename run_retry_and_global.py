#!/usr/bin/env python3
"""
1. Re-run all gpt-4.1-mini rounds that have score=None
2. Then run gpt-4o-global × 5 rounds × all 13 tasks
All in parallel, max 20 workers.
"""
from __future__ import annotations

import json
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT      = Path(__file__).resolve().parent
NEW_LOGS  = ROOT / "logs" / "multi_bench"

LOCAL_BASE_URL = "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/"
LOCAL_API_KEY  = "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk"

MAX_PARALLEL = 20

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
        f"  ✅ r{round_num:02d} {model:<14} {short:<22} score={score_s}  {elapsed/60:.1f}m  [{status}]",
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


def find_mini_retries() -> list[tuple[str, str, int]]:
    """Find all gpt-4.1-mini rounds with score=None."""
    retries = []
    model = "gpt-4.1-mini"
    for task in ALL_TASKS:
        for rnd in range(1, 6):
            sidecar = NEW_LOGS / model / task / f"round_{rnd:02d}" / "_timing.json"
            if sidecar.exists():
                try:
                    d = json.loads(sidecar.read_text())
                    if d.get("score") is None:
                        retries.append((model, task, rnd))
                except Exception:
                    retries.append((model, task, rnd))
    return retries


def main() -> None:
    # --- Phase 1: retry gpt-4.1-mini None-score runs ---
    retries = find_mini_retries()
    print(f"\n📋 Phase 1: {len(retries)} gpt-4.1-mini retries (score=None rounds)")
    for m, t, r in retries:
        print(f"     {t}  r{r}")

    # --- Phase 2: gpt-4o-global 5 rounds × 13 tasks ---
    global_jobs = [("gpt-4o-global", task, rnd)
                   for rnd in range(1, 6)
                   for task in ALL_TASKS]
    print(f"\n📋 Phase 2: {len(global_jobs)} gpt-4o-global jobs (5 rounds × 13 tasks)")

    all_jobs = retries + global_jobs
    total = len(all_jobs)
    print(f"\n🚀 {total} total evals queued  ({MAX_PARALLEL} max parallel)\n")
    print(f"  {'Rnd':<4} {'Model':<14} {'Task':<22}  Result")
    print(f"  {'-'*4} {'-'*14} {'-'*22}  {'-'*35}")

    completed = 0
    wall_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {
            pool.submit(run_eval, model, task, rnd): (model, task, rnd)
            for model, task, rnd in all_jobs
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


if __name__ == "__main__":
    main()
