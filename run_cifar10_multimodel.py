#!/usr/bin/env python3
"""Run cifar10-burn-optimise against multiple model configs (3 runs each) sequentially.

Models tested:
  gpt-4.1-mini, gpt-5, gpt-5.2, gpt-5.4, gpt-5-low, gpt-5-high

Usage:
    uv run python run_cifar10_multimodel.py
    uv run python run_cifar10_multimodel.py --report-only
    uv run python run_cifar10_multimodel.py --models gpt-5.2,gpt-5.4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import time
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "closed-terminal-bench"
LOGS_BASE = ROOT / "logs" / "cifar10_multimodel"
RESULTS_FILE = ROOT / "logs" / "cifar10_multimodel_results.json"
REPORT_FILE = ROOT / "logs" / "cifar10_multimodel_report.txt"

TASK = "cifar10-burn-optimise"
ROUNDS = 3

LOCAL_BASE_URL = os.environ.get(
    "LOCAL_BASE_URL",
    "https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/",
)
LOCAL_API_KEY = os.environ.get(
    "LOCAL_API_KEY",
    "4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk",
)


@dataclass
class ModelConfig:
    name: str               # short label (e.g. "gpt-5-low")
    model_id: str           # inspect model string
    extra_args: list[str] = field(default_factory=list)  # e.g. ["--reasoning-effort", "low"]


MODEL_CONFIGS: list[ModelConfig] = [
    ModelConfig("gpt-4.1-mini",  "openai-api/local/gpt-4.1-mini"),
    ModelConfig("gpt-5",         "openai-api/local/gpt-5"),
    ModelConfig("gpt-5.2",       "openai-api/local/gpt-5.2"),
    ModelConfig("gpt-5.4",       "openai-api/local/gpt-5.4"),
    ModelConfig("gpt-5-low",     "openai-api/local/gpt-5",  ["--reasoning-effort", "low"]),
    ModelConfig("gpt-5-high",    "openai-api/local/gpt-5",  ["--reasoning-effort", "high"]),
]


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def docker_prune() -> None:
    result = subprocess.run(
        ["docker", "network", "prune", "-f"], capture_output=True, text=True
    )
    msg = result.stdout.strip() or "(no output)"
    print(f"  [docker prune] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Eval runner
# ---------------------------------------------------------------------------

def run_eval(cfg: ModelConfig, run_num: int) -> tuple[Path, float]:
    """Run one eval. Returns (log_dir, elapsed_seconds)."""
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

    print(f"    [{cfg.name} run={run_num}] Starting...", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=3600)
    elapsed = time.time() - t0

    if result.returncode != 0:
        tail = result.stderr[-600:] if result.stderr else "(no stderr)"
        print(f"    [{cfg.name} run={run_num}] FAILED (rc={result.returncode}) in {elapsed:.0f}s:\n{tail}", flush=True)
    else:
        print(f"    [{cfg.name} run={run_num}] Done in {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)

    return log_dir, elapsed


# ---------------------------------------------------------------------------
# Eval file parsing
# ---------------------------------------------------------------------------

def parse_score(eval_path: Path) -> float | None:
    """Extract the mean/accuracy score from an eval zip."""
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


def parse_detail(eval_path: Path) -> dict:
    """Extract step pass/fail, failed test names, and key error snippets."""
    detail: dict = {
        "overall_score": None,
        "overall_answer": None,
        "steps": {},   # step_label -> {result, passed, total, failed_tests, snippet}
    }
    try:
        with zipfile.ZipFile(eval_path, "r") as zf:
            sample_names = [n for n in zf.namelist() if "sample" in n and n.endswith(".json")]
            if not sample_names:
                return detail
            d = json.loads(zf.read(sample_names[0]))
    except Exception:
        return detail

    for scorer_name, sdata in d.get("scores", {}).items():
        detail["overall_score"] = sdata.get("value")
        detail["overall_answer"] = sdata.get("answer")
        expl = sdata.get("explanation", "")

        # Parse explanation — it's the harness stdout containing step blocks
        # Pattern: step labels like "step1:", "step2:", etc. with pytest summary
        step_blocks = re.split(r'\n(?=step\d+:)', expl)
        for block in step_blocks:
            m = re.match(r'(step\d+):\s*(pass|fail)', block)
            if not m:
                continue
            label = m.group(1)
            result = m.group(2)

            # Count passed/failed from pytest summary line
            passed_m = re.search(r'(\d+) passed', block)
            failed_m = re.search(r'(\d+) failed', block)
            total_passed = int(passed_m.group(1)) if passed_m else 0
            total_failed = int(failed_m.group(1)) if failed_m else 0

            # Extract FAILED test names
            failed_tests = re.findall(r'FAILED\s+([\w/\.]+::\w+)', block)

            # Extract short assertion snippet per failed test
            snippets: list[str] = []
            for ft in failed_tests:
                test_name = ft.split("::")[-1]
                # Find AssertionError line near the test
                ae_m = re.search(
                    rf'{re.escape(test_name)}.*?AssertionError: ([^\n]{{1,120}})',
                    block, re.DOTALL
                )
                if ae_m:
                    snippets.append(f"{test_name}: {ae_m.group(1).strip()}")
                else:
                    snippets.append(test_name)

            detail["steps"][label] = {
                "result": result,
                "passed": total_passed,
                "failed": total_failed,
                "total": total_passed + total_failed,
                "failed_tests": failed_tests,
                "snippets": snippets,
            }
    return detail


def collect_run_results(cfg: ModelConfig) -> list[dict]:
    """Collect scores and details for all 3 runs of a given model config."""
    runs = []
    for run_num in range(1, ROUNDS + 1):
        log_dir = LOGS_BASE / cfg.name / f"run_{run_num:02d}"
        eval_files = sorted(log_dir.glob("*.eval")) if log_dir.exists() else []
        if not eval_files:
            runs.append({"run": run_num, "score": None, "elapsed": None, "detail": {}})
            continue
        score = parse_score(eval_files[0])
        detail = parse_detail(eval_files[0])
        runs.append({"run": run_num, "score": score, "elapsed": None, "detail": detail})
    return runs


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_report(all_results: dict[str, list[dict]]) -> str:
    lines: list[str] = []

    lines.append("=" * 72)
    lines.append("cifar10-burn-optimise  MULTI-MODEL COMPARISON")
    lines.append(f"Image: local/cifar10-burn-optimise:20260326  (rustc 1.94.1 stable)")
    lines.append("=" * 72)
    lines.append("")

    # Summary table
    lines.append(f"{'Model':<18} {'Run1':>6} {'Run2':>6} {'Run3':>6}  {'Mean':>6}  {'Std':>6}  {'Min t':>7}  {'Max t':>7}")
    lines.append("-" * 72)

    summary_rows = []
    for cfg_name, runs in all_results.items():
        scores = [r["score"] for r in runs if r["score"] is not None]
        times  = [r["elapsed"] for r in runs if r["elapsed"] is not None]
        mean   = statistics.mean(scores) if scores else float("nan")
        std    = statistics.stdev(scores) if len(scores) >= 2 else float("nan")
        min_t  = min(times) / 60 if times else float("nan")
        max_t  = max(times) / 60 if times else float("nan")

        score_strs = [f"{r['score']:.4f}" if r["score"] is not None else "  n/a " for r in runs]
        mean_s = f"{mean:.4f}" if not (mean != mean) else "  n/a"
        std_s  = f"{std:.4f}" if not (std != std) else "  n/a"
        min_ts = f"{min_t:.1f}m" if not (min_t != min_t) else "  n/a"
        max_ts = f"{max_t:.1f}m" if not (max_t != max_t) else "  n/a"

        lines.append(
            f"{cfg_name:<18} {score_strs[0]:>6} {score_strs[1]:>6} {score_strs[2]:>6}  "
            f"{mean_s:>6}  {std_s:>6}  {min_ts:>7}  {max_ts:>7}"
        )
        summary_rows.append((cfg_name, mean, std, scores))

    lines.append("")

    # Scoring scale reminder
    lines.append("Score scale:  step1 fail=0  |  step1 pass=0.333  |  step1+2 pass=0.667  |  all pass=1.0")
    lines.append("")

    # Per-model detail
    for cfg_name, runs in all_results.items():
        lines.append("─" * 72)
        lines.append(f"  {cfg_name}")
        lines.append("─" * 72)
        for r in runs:
            score_s = f"{r['score']:.4f}" if r["score"] is not None else "n/a"
            time_s  = f"{r['elapsed']/60:.1f}m" if r["elapsed"] else "n/a"
            lines.append(f"  Run {r['run']}: score={score_s}  time={time_s}")
            steps = r.get("detail", {}).get("steps", {})
            for step_label in sorted(steps):
                s = steps[step_label]
                icon = "✅" if s["result"] == "pass" else "❌"
                lines.append(f"    {icon} {step_label}: {s['result']}  ({s['passed']}/{s['total']})")
                for snip in s.get("snippets", []):
                    lines.append(f"       ↳ {snip[:110]}")
        lines.append("")

    # Analysis
    lines.append("=" * 72)
    lines.append("ANALYSIS")
    lines.append("=" * 72)
    lines.append("")

    # Rank by mean
    ranked = sorted(
        summary_rows,
        key=lambda x: x[1] if x[1] == x[1] else -1,
        reverse=True,
    )
    lines.append("Ranking by mean score:")
    for i, (name, mean, std, scores) in enumerate(ranked, 1):
        mean_s = f"{mean:.4f}" if mean == mean else "n/a"
        std_s  = f"±{std:.4f}" if std == std else ""
        lines.append(f"  {i}. {name:<18} {mean_s} {std_s}")
    lines.append("")

    # Common failure patterns
    lines.append("Common failure patterns:")
    failure_counts: dict[str, dict[str, int]] = {}
    for cfg_name, runs in all_results.items():
        for r in runs:
            for step_label, s in r.get("detail", {}).get("steps", {}).items():
                for ft in s.get("failed_tests", []):
                    failure_counts.setdefault(ft, {})
                    failure_counts[ft][cfg_name] = failure_counts[ft].get(cfg_name, 0) + 1

    if failure_counts:
        total_runs = len(all_results) * ROUNDS
        sorted_failures = sorted(failure_counts.items(), key=lambda x: sum(x[1].values()), reverse=True)
        for test_name, counts in sorted_failures[:10]:
            total = sum(counts.values())
            pct = 100 * total / total_runs
            models_hit = ", ".join(f"{m}×{n}" for m, n in sorted(counts.items()))
            lines.append(f"  {total:>2}/{total_runs} ({pct:4.0f}%)  {test_name}")
            lines.append(f"            affected: {models_hit}")
    else:
        lines.append("  (no failures)")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true",
                        help="Skip running evals, just parse existing logs")
    parser.add_argument("--models", default="",
                        help="Comma-separated subset of model names to run, e.g. gpt-5.2,gpt-5.4")
    args = parser.parse_args()

    # Filter model configs if requested
    selected_names = {n.strip() for n in args.models.split(",") if n.strip()}
    configs = [c for c in MODEL_CONFIGS if not selected_names or c.name in selected_names]

    if not args.report_only:
        LOGS_BASE.mkdir(parents=True, exist_ok=True)
        print(f"Running cifar10-burn-optimise × {ROUNDS} for {len(configs)} model configs sequentially\n")

        for cfg in configs:
            print(f"\n{'━'*50}")
            print(f"  Model: {cfg.name}  ({cfg.model_id}  {' '.join(cfg.extra_args)})")
            print(f"{'━'*50}")
            elapsed_times: list[float] = []

            for run_num in range(1, ROUNDS + 1):
                if run_num > 1:
                    docker_prune()
                log_dir, elapsed = run_eval(cfg, run_num)
                elapsed_times.append(elapsed)

                # Store elapsed back into a sidecar file for report-only mode
                sidecar = log_dir / "_timing.json"
                sidecar.write_text(json.dumps({"elapsed": elapsed}))

            docker_prune()

        print("\n\nAll runs complete.\n")

    # Collect results
    all_results: dict[str, list[dict]] = {}
    for cfg in configs:
        runs = collect_run_results(cfg)
        # Re-attach timing from sidecar files if present
        for r in runs:
            log_dir = LOGS_BASE / cfg.name / f"run_{r['run']:02d}"
            sidecar = log_dir / "_timing.json"
            if sidecar.exists():
                try:
                    r["elapsed"] = json.loads(sidecar.read_text())["elapsed"]
                except Exception:
                    pass
        all_results[cfg.name] = runs

    # Save raw JSON
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"Raw results saved → {RESULTS_FILE}")

    # Build and save text report
    report = format_report(all_results)
    REPORT_FILE.write_text(report)
    print(f"Report saved      → {REPORT_FILE}\n")
    print(report)


if __name__ == "__main__":
    main()
