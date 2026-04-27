#!/usr/bin/env python3
"""Unified benchmark runner for terminal-bench tasks.

Runs each task as a separate inspect eval (isolated token tracking per task).
Auto-discovers tasks from terminal-bench/*/run.py.

Usage:
    uv run python run_bench.py                                    # all tasks, gpt-5, 1 round
    uv run python run_bench.py --tasks pokemon-battle-fix,ext4-recovery
    uv run python run_bench.py --models gpt-5,gpt-5.4 --rounds 3
    uv run python run_bench.py --parallel 10
    uv run python run_bench.py --report-only
    uv run python run_bench.py --report-only --log-dir logs/bench
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "terminal-bench"
DEFAULT_LOG_DIR = ROOT / "logs" / "bench"


def discover_tasks() -> list[str]:
    """Find all terminal-bench tasks that have a run.py."""
    tasks = []
    for run_py in sorted(BENCH_DIR.glob("*/run.py")):
        name = run_py.parent.name
        if name == "common":
            continue
        tasks.append(name)
    return tasks


def read_task_timeout(task: str) -> int:
    """Read agent_timeout_sec from eval.yaml, default 3600."""
    eval_yaml = BENCH_DIR / task / "eval.yaml"
    if eval_yaml.exists():
        import re
        text = eval_yaml.read_text()
        m = re.search(r"agent_timeout_sec:\s*(\d+)", text)
        if m:
            return int(m.group(1))
    return 3600


def parse_eval_file(eval_path: Path) -> dict:
    """Extract score and token usage from an .eval zip file."""
    result: dict = {"score": None, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
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

                # Score from results.scores
                if result["score"] is None:
                    for entry in data.get("results", {}).get("scores", []):
                        for mname, mdata in entry.get("metrics", {}).items():
                            if mname in ("accuracy", "mean"):
                                val = mdata.get("value")
                                if val is not None:
                                    try:
                                        result["score"] = float(val)
                                    except (ValueError, TypeError):
                                        pass

                # Token usage from stats.model_usage (header.json)
                model_usage = data.get("stats", {}).get("model_usage", {})
                for _model_id, usage in model_usage.items():
                    result["input_tokens"] += usage.get("input_tokens", 0)
                    result["output_tokens"] += usage.get("output_tokens", 0)
                    result["total_tokens"] += usage.get("total_tokens", 0)
    except Exception:
        pass
    return result


def get_env_credentials() -> tuple[str, str]:
    """Read API credentials from environment (.env loaded by caller or shell)."""
    base_url = os.environ.get("LOCAL_BASE_URL", "")
    api_key = os.environ.get("LOCAL_API_KEY", "")
    if not base_url or not api_key:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key == "LOCAL_BASE_URL" and not base_url:
                    base_url = val
                elif key == "LOCAL_API_KEY" and not api_key:
                    api_key = val
    return base_url, api_key


def run_eval(
    model: str,
    task: str,
    round_num: int,
    log_base: Path,
    base_url: str,
    api_key: str,
) -> dict:
    """Run a single task eval. Returns result dict."""
    log_dir = log_base / model / task / f"round_{round_num:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    timeout = read_task_timeout(task)
    task_spec = f"terminal-bench/{task}/run.py"

    cmd = [
        "uv", "run", "inspect", "eval",
        task_spec,
        "--model", f"openai-api/local/{model}",
        "--env", f"LOCAL_BASE_URL={base_url}",
        "--env", f"LOCAL_API_KEY={api_key}",
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
    parsed = parse_eval_file(eval_files[0]) if eval_files else {"score": None, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    score = parsed["score"]
    status = "ok" if rc == 0 else f"FAIL(rc={rc})"
    score_s = f"{score:.3f}" if score is not None else " n/a"
    tokens_s = f"{parsed['total_tokens']:,}" if parsed["total_tokens"] else "n/a"

    print(
        f"  r{round_num:02d}  {model:<16} {task:<32} score={score_s}  tokens={tokens_s}  {elapsed/60:.1f}m  [{status}]",
        flush=True,
    )
    if stderr_tail and rc != 0:
        print(f"       stderr: {stderr_tail[:200]}", flush=True)

    sidecar = {
        "model": model,
        "task": task,
        "round": round_num,
        "elapsed": round(elapsed, 1),
        "rc": rc,
        "score": score,
        "input_tokens": parsed["input_tokens"],
        "output_tokens": parsed["output_tokens"],
        "total_tokens": parsed["total_tokens"],
    }
    (log_dir / "_timing.json").write_text(json.dumps(sidecar, indent=2))

    return sidecar


def load_results(log_base: Path) -> list[dict]:
    """Load all _timing.json sidecars from a log directory."""
    results = []
    for sidecar in sorted(log_base.rglob("_timing.json")):
        try:
            d = json.loads(sidecar.read_text())
            results.append(d)
        except Exception:
            pass
    return results


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def build_report(results: list[dict], tasks: list[str], models: list[str]) -> str:
    """Build a results report table."""
    scores: dict[tuple[str, str], list[dict]] = {}
    for r in results:
        k = (r["model"], r["task"])
        scores.setdefault(k, []).append(r)

    lines: list[str] = []

    for model in models:
        model_tasks = [t for t in tasks if scores.get((model, t))]
        if not model_tasks:
            continue

        lines.append("")
        lines.append(f"  terminal-bench results — {model}")
        lines.append(f"  {'─' * 76}")
        lines.append(f"  {'Task':<34} {'Avg':>6} {'Max':>6} {'Rounds':>8} {'Tokens':>10}")
        lines.append(f"  {'─' * 76}")

        all_avgs = []
        all_maxs = []
        total_tokens = 0
        total_rounds = 0

        for task in tasks:
            runs = scores.get((model, task), [])
            valid = [r for r in runs if r.get("score") is not None]
            if not valid:
                lines.append(f"  {task:<34} {'—':>6} {'—':>6} {'0':>8} {'—':>10}")
                continue

            avg_score = sum(r["score"] for r in valid) / len(valid)
            max_score = max(r["score"] for r in valid)
            n = len(valid)
            tok = sum(r.get("total_tokens", 0) for r in valid)

            all_avgs.append(avg_score)
            all_maxs.append(max_score)
            total_tokens += tok
            total_rounds += n

            lines.append(
                f"  {task:<34} {avg_score:>6.3f} {max_score:>6.3f} {n:>8} {fmt_tokens(tok):>10}"
            )

        lines.append(f"  {'─' * 76}")

        if all_avgs:
            avg_of_avgs = sum(all_avgs) / len(all_avgs)
            avg_of_maxs = sum(all_maxs) / len(all_maxs)
            lines.append(
                f"  {'AVERAGE':<34} {avg_of_avgs:>6.3f} {avg_of_maxs:>6.3f} {total_rounds:>8} {fmt_tokens(total_tokens):>10}"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run terminal-bench evaluations")
    parser.add_argument("--tasks", default="", help="Comma-separated task names (default: all)")
    parser.add_argument("--models", default="gpt-5", help="Comma-separated model names (default: gpt-5)")
    parser.add_argument("--rounds", type=int, default=1, help="Number of rounds per task (default: 1)")
    parser.add_argument("--parallel", type=int, default=5, help="Max parallel evals (default: 5)")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Log directory")
    parser.add_argument("--report-only", action="store_true", help="Just report on existing logs")
    args = parser.parse_args()

    log_base = Path(args.log_dir)
    all_tasks = discover_tasks()
    sel_tasks = [t.strip() for t in args.tasks.split(",") if t.strip()] if args.tasks else all_tasks
    sel_models = [m.strip() for m in args.models.split(",") if m.strip()]

    bad = [t for t in sel_tasks if t not in all_tasks]
    if bad:
        print(f"Unknown tasks: {', '.join(bad)}")
        print(f"Available: {', '.join(all_tasks)}")
        return

    if args.report_only:
        results = load_results(log_base)
        if not results:
            print(f"No results found in {log_base}")
            return
        found_models = sorted({r["model"] for r in results})
        found_tasks = sorted({r["task"] for r in results})
        report = build_report(results, found_tasks, found_models)
        print(report)

        out = log_base / "report.txt"
        out.write_text(report)
        print(f"  Report saved: {out}")
        return

    base_url, api_key = get_env_credentials()
    if not base_url or not api_key:
        print("Missing LOCAL_BASE_URL or LOCAL_API_KEY. Set in .env or environment.")
        return

    log_base.mkdir(parents=True, exist_ok=True)

    jobs = [
        (model, task, rnd)
        for rnd in range(1, args.rounds + 1)
        for model in sel_models
        for task in sel_tasks
    ]
    total = len(jobs)

    print(f"\n  {total} evals queued ({args.parallel} max parallel)")
    print(f"  Models: {', '.join(sel_models)}")
    print(f"  Tasks:  {len(sel_tasks)} x {args.rounds} round(s)")
    print(f"  Logs:   {log_base}\n")

    wall_start = time.time()
    completed = 0

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = {
            pool.submit(run_eval, model, task, rnd, log_base, base_url, api_key): (model, task, rnd)
            for model, task, rnd in jobs
        }
        for fut in as_completed(futures):
            model, task, rnd = futures[fut]
            try:
                fut.result()
            except Exception as e:
                print(f"  ERROR r{rnd:02d} {model} / {task}: {e}", flush=True)
            completed += 1
            if completed % 5 == 0 or completed == total:
                print(f"  [{completed}/{total} done]", flush=True)

    wall = time.time() - wall_start
    print(f"\n  All {total} evals done in {wall / 60:.1f} min\n")

    results = load_results(log_base)
    report = build_report(results, sel_tasks, sel_models)
    print(report)

    out = log_base / "report.txt"
    out.write_text(report)
    print(f"  Report saved: {out}")

    raw = log_base / "results.json"
    raw.write_text(json.dumps(results, indent=2, default=str))
    print(f"  Results JSON: {raw}")


if __name__ == "__main__":
    main()
