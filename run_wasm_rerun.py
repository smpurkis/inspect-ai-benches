#!/usr/bin/env python3
"""
Re-run wasm-compression-stepwise for gpt-4.1-mini and gpt-4o-global (5 rounds each).
These runs were contaminated by the pytest hang bug (no per-test timeout + full 900KB files).
Fixes now in place:
  - pytest-timeout installed in wasm image (20260328)
  - --timeout=900 in staged_eval.py
  - wasm step_1 hidden tests use 90KB/110KB slices instead of 900KB/1.1MB
  - cpus: 8 in compose.yaml (was 2)
All 10 runs go in parallel (both use Azure API).
"""
from __future__ import annotations

import json
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
NEW_LOGS = ROOT / "logs" / "multi_bench"

LOCAL_BASE_URL = "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/"
LOCAL_API_KEY  = "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk"

TASK         = "wasm-compression-stepwise"
TASK_TIMEOUT = 3600
ROUNDS       = 5
MODELS       = ["gpt-4.1-mini", "gpt-4o-global"]
MAX_PARALLEL = 10   # 10 runs total, all parallel


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
        pass
    return None


def run_eval(model: str, round_num: int) -> dict:
    log_dir = NEW_LOGS / model / TASK / f"round_{round_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)
    task_spec = f"closed-terminal-bench/{TASK}/run.py@run"

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
            cwd=str(ROOT), timeout=TASK_TIMEOUT + 300,
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
    print(
        f"  ✅ r{round_num:02d} {model:<20} wasm-compress  score={score_s}  {elapsed/60:.1f}m  [{status}]",
        flush=True,
    )
    if stderr_tail and rc != 0:
        print(f"       stderr: {stderr_tail[:200]}", flush=True)

    sidecar = log_dir / "_timing.json"
    sidecar.write_text(json.dumps({
        "model": model, "task": TASK, "round": round_num,
        "elapsed": elapsed, "rc": rc, "score": score,
    }))

    return {"model": model, "round": round_num, "score": score, "elapsed": elapsed, "rc": rc}


def main() -> None:
    jobs = [(model, rnd) for model in MODELS for rnd in range(1, ROUNDS + 1)]
    print(f"Launching {len(jobs)} wasm-compression-stepwise reruns in parallel...\n")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(run_eval, model, rnd): (model, rnd) for model, rnd in jobs}
        for fut in as_completed(futures):
            model, rnd = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"  ❌ r{rnd:02d} {model} wasm: {e}", flush=True)

    # Summary table
    print("\n" + "=" * 60)
    print("FINAL RESULTS — wasm-compression-stepwise")
    print("=" * 60)
    for model in MODELS:
        model_results = sorted([r for r in results if r["model"] == model], key=lambda r: r["round"])
        scores = [r["score"] for r in model_results if r["score"] is not None]
        print(f"\n{model}:")
        for r in model_results:
            s = f"{r['score']:.4f}" if r["score"] is not None else "  None"
            print(f"  r{r['round']:02d}  score={s}  {r['elapsed']/60:.1f}m")
        if scores:
            avg = sum(scores) / len(scores)
            top1 = max(scores)
            sorted_s = sorted(scores)
            mid3 = sum(sorted_s[1:-1]) / len(sorted_s[1:-1]) if len(sorted_s) >= 3 else avg
            print(f"  avg={avg:.4f}  top1={top1:.4f}  mid3={mid3:.4f}")
        else:
            print("  (no valid scores)")


if __name__ == "__main__":
    main()
