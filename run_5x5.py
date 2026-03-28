#!/usr/bin/env python3
"""Run cifar10-burn-optimise: 5x gpt-5 then 5x gpt-5.4, 5 parallel at a time.

Usage:
    python3 run_5x5.py
    python3 run_5x5.py --report-only
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs" / "run_5x5"

LOCAL_BASE_URL = os.environ.get(
    "LOCAL_BASE_URL",
    "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/",
)
LOCAL_API_KEY = os.environ.get(
    "LOCAL_API_KEY",
    "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk",
)

MODELS = [
    ("gpt-5",   "openai-api/local/gpt-5"),
    ("gpt-5.4", "openai-api/local/gpt-5.4"),
]
RUNS = 5
PARALLEL = 5


def run_eval(model_name: str, model_id: str, run_num: int) -> dict:
    log_dir = LOGS_DIR / model_name / f"run_{run_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "uv", "run", "inspect", "eval",
        "closed-terminal-bench/cifar10-burn-optimise/run.py@run",
        "--model", model_id,
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--max-tasks", "1",
        "--display", "none",
    ]

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=3600)
    elapsed = time.time() - t0

    score = None
    for ef in sorted(log_dir.glob("*.eval")):
        score = extract_score(ef)
        if score is not None:
            break

    status = "ok" if result.returncode == 0 else f"rc={result.returncode}"
    print(f"  [{model_name} #{run_num}] {status}  score={score}  {elapsed/60:.1f}m", flush=True)

    # save timing sidecar
    (log_dir / "_timing.json").write_text(json.dumps({"elapsed": elapsed, "score": score}))
    return {"model": model_name, "run": run_num, "score": score, "elapsed": elapsed}


def extract_score(path: Path) -> float | None:
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    data = json.loads(zf.read(name))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for se in data.get("results", {}).get("scores", []):
                    if not isinstance(se, dict):
                        continue
                    for mn, md in se.get("metrics", {}).items():
                        if mn in ("accuracy", "mean") and isinstance(md, dict):
                            v = md.get("value")
                            if v is not None:
                                try:
                                    return float(v)
                                except Exception:
                                    pass
    except Exception:
        pass
    return None


def print_report(all_results: dict[str, list[dict]]) -> None:
    print()
    print("=" * 60)
    print("cifar10-burn-optimise  5×5  results")
    print("=" * 60)
    for model_name, runs in all_results.items():
        scores = [r["score"] for r in runs if r["score"] is not None]
        times  = [r["elapsed"] / 60 for r in runs if r["elapsed"] is not None]
        mean = statistics.mean(scores) if scores else float("nan")
        std  = statistics.stdev(scores) if len(scores) > 1 else 0.0
        mn   = min(scores) if scores else float("nan")
        mx   = max(scores) if scores else float("nan")
        run_scores = "  ".join(f"{r['score']:.4f}" if r["score"] is not None else " n/a " for r in runs)
        print(f"\n  {model_name}  (n={len(scores)})")
        print(f"  Runs:  {run_scores}")
        print(f"  Mean:  {mean:.4f}   Std: {std:.4f}   Min: {mn:.4f}   Max: {mx:.4f}")
        if times:
            print(f"  Times: {' '.join(f'{t:.1f}m' for t in times)}   avg={statistics.mean(times):.1f}m")
    print()

    # side-by-side comparison
    models = list(all_results.keys())
    if len(models) == 2:
        s1 = [r["score"] for r in all_results[models[0]] if r["score"] is not None]
        s2 = [r["score"] for r in all_results[models[1]] if r["score"] is not None]
        print(f"  {models[0]:<12} mean={statistics.mean(s1):.4f}  std={statistics.stdev(s1):.4f}")
        print(f"  {models[1]:<12} mean={statistics.mean(s2):.4f}  std={statistics.stdev(s2):.4f}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    all_results: dict[str, list[dict]] = {}

    if args.report_only:
        for model_name, _ in MODELS:
            runs = []
            for i in range(1, RUNS + 1):
                log_dir = LOGS_DIR / model_name / f"run_{i:02d}"
                sidecar = log_dir / "_timing.json"
                if sidecar.exists():
                    d = json.loads(sidecar.read_text())
                    runs.append({"model": model_name, "run": i, "score": d.get("score"), "elapsed": d.get("elapsed")})
                else:
                    evals = list(log_dir.glob("*.eval")) if log_dir.exists() else []
                    score = extract_score(evals[0]) if evals else None
                    runs.append({"model": model_name, "run": i, "score": score, "elapsed": None})
            all_results[model_name] = runs
        print_report(all_results)
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    for model_name, model_id in MODELS:
        print(f"\n{'━'*50}")
        print(f"  {model_name}  —  {RUNS} runs, {PARALLEL} parallel")
        print(f"{'━'*50}")

        jobs = [(model_name, model_id, i) for i in range(1, RUNS + 1)]
        results = []

        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            futures = {pool.submit(run_eval, mn, mid, i): (mn, i) for mn, mid, i in jobs}
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:
                    mn, i = futures[fut]
                    print(f"  [{mn} #{i}] ERROR: {e}", flush=True)
                    results.append({"model": mn, "run": i, "score": None, "elapsed": None})

        results.sort(key=lambda r: r["run"])
        all_results[model_name] = results

        # prune networks between model batches
        subprocess.run(["docker", "network", "prune", "-f"], capture_output=True)
        print(f"  [docker] networks pruned", flush=True)

    # Save JSON
    out = LOGS_DIR / "results.json"
    out.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\nResults saved → {out}")

    print_report(all_results)


if __name__ == "__main__":
    main()
