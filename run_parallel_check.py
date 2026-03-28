#!/usr/bin/env python3
"""Run gpt-5 and gpt-5.4 in parallel on cifar10-burn-optimise as a network_mode:host stress check.

Prints a status line each time a run completes.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_BASE = ROOT / "logs" / "parallel_check"

TASK = "cifar10-burn-optimise"
ROUNDS = 1  # single round per model for the sanity check

LOCAL_BASE_URL = "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/"
LOCAL_API_KEY  = "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk"


@dataclass
class ModelConfig:
    name: str
    model_id: str
    extra_args: list[str] = field(default_factory=list)


MODEL_CONFIGS: list[ModelConfig] = [
    ModelConfig("gpt-5",   "openai-api/local/gpt-5"),
    ModelConfig("gpt-5.4", "openai-api/local/gpt-5.4"),
]


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
    except zipfile.BadZipFile:
        return None
    return None


def run_eval(cfg: ModelConfig, run_num: int) -> dict:
    log_dir = LOGS_BASE / cfg.name / f"run_{run_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    task_spec = f"closed-terminal-bench/{TASK}/run.py@run"
    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", cfg.model_id,
        "--env", f"LOCAL_BASE_URL={LOCAL_BASE_URL}",
        "--env", f"LOCAL_API_KEY={LOCAL_API_KEY}",
        "--log-dir", str(log_dir),
        "--max-tasks", "1",
        "--display", "none",
        *cfg.extra_args,
    ]

    print(f"  [{cfg.name}] Starting run {run_num}...", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=3600)
    elapsed = time.time() - t0

    # Parse score
    eval_files = sorted(log_dir.glob("*.eval"))
    score = parse_score(eval_files[0]) if eval_files else None

    status = "OK" if result.returncode == 0 else f"FAILED rc={result.returncode}"
    score_s = f"{score:.4f}" if score is not None else "n/a"

    print(
        f"\n{'='*60}\n"
        f"  ✅ COMPLETE: {cfg.name} run {run_num}\n"
        f"     Status : {status}\n"
        f"     Score  : {score_s}\n"
        f"     Time   : {elapsed:.0f}s ({elapsed/60:.1f}m)\n"
        f"{'='*60}",
        flush=True,
    )

    if result.returncode != 0:
        tail = result.stderr[-800:] if result.stderr else "(no stderr)"
        print(f"  STDERR tail:\n{tail}", flush=True)

    # Save timing sidecar
    (log_dir / "_timing.json").write_text(json.dumps({
        "elapsed": elapsed,
        "returncode": result.returncode,
        "score": score,
    }))

    return {"name": cfg.name, "run": run_num, "score": score, "elapsed": elapsed, "rc": result.returncode}


def main() -> None:
    LOGS_BASE.mkdir(parents=True, exist_ok=True)
    print(f"🚀 Launching {len(MODEL_CONFIGS)} models in parallel on {TASK}")
    print(f"   Models: {', '.join(c.name for c in MODEL_CONFIGS)}\n")

    t_start = time.time()
    futures = {}
    results = []

    with ThreadPoolExecutor(max_workers=len(MODEL_CONFIGS)) as pool:
        for cfg in MODEL_CONFIGS:
            for run_num in range(1, ROUNDS + 1):
                fut = pool.submit(run_eval, cfg, run_num)
                futures[fut] = (cfg.name, run_num)

        for fut in as_completed(futures):
            try:
                res = fut.result()
                results.append(res)
            except Exception as e:
                name, run_num = futures[fut]
                print(f"\n❌ ERROR: {name} run {run_num}: {e}", flush=True)
                results.append({"name": name, "run": run_num, "score": None, "elapsed": None, "rc": -1})

    total_elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"ALL DONE in {total_elapsed:.0f}s ({total_elapsed/60:.1f}m)")
    print(f"{'='*60}")
    print(f"\n{'Model':<12} {'Run':>4} {'Score':>8} {'Time':>8} {'Status':>10}")
    print("-" * 50)
    for r in sorted(results, key=lambda x: (x["name"], x["run"])):
        score_s = f"{r['score']:.4f}" if r["score"] is not None else "   n/a"
        time_s  = f"{r['elapsed']/60:.1f}m" if r["elapsed"] else "   n/a"
        status  = "OK" if r["rc"] == 0 else f"FAIL({r['rc']})"
        print(f"{r['name']:<12} {r['run']:>4} {score_s:>8} {time_s:>8} {status:>10}")

    # Save summary JSON
    summary_path = LOGS_BASE / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nSummary saved → {summary_path}")


if __name__ == "__main__":
    main()
