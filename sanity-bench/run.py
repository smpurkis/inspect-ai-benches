#!/usr/bin/env python3
"""Sanity-bench runner.

Token-efficient sanity check of an OpenAI-compatible endpoint across a wide
range of capability axes. One HTTP call per task, deterministic scoring,
per-task sidecar JSON, summary report.

Example:
    LOCAL_BASE_URL=http://localhost:8234/v1 \\
    LOCAL_API_KEY=secret \\
    uv run python sanity-bench/run.py --model my-model --parallel 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from openai import AsyncOpenAI
from openai import APIError

from scoring import SCORERS, score as score_response, strip_thinking


ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT / "tasks"
DEFAULT_LOG_DIR = ROOT.parent / "logs" / "sanity"


def _load_tasks(categories: list[str] | None, task_ids: list[str] | None) -> list[dict]:
    out: list[dict] = []
    files = sorted(TASKS_DIR.glob("*.yaml"))
    for fp in files:
        data = yaml.safe_load(fp.read_text()) or {}
        cat = data.get("category") or fp.stem
        if categories and cat not in categories:
            continue
        for t in data.get("tasks", []):
            t["category"] = cat
            if task_ids and t["id"] not in task_ids:
                continue
            out.append(t)
    return out


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


async def _judge(client: AsyncOpenAI, judge_model: str, task: dict, response: str) -> tuple[float, str]:
    """LLM-as-judge scoring. Returns (score, explanation)."""
    rubric = task["scoring"].get("rubric", "Rate the response on a 0-1 scale.")
    prompt_text = task.get("prompt", "")
    judge_prompt = f"""You are grading a model's response. Output ONLY one of these scores: 0.0, 0.25, 0.5, 0.75, 1.0

Rubric:
{rubric}

The original task:
{prompt_text}

The model's response:
\"\"\"
{strip_thinking(response)}
\"\"\"

Reply with just a single number from the set [0.0, 0.25, 0.5, 0.75, 1.0]."""
    try:
        resp = await client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": judge_prompt}],
            max_completion_tokens=64,
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return (0.0, f"judge call failed: {type(e).__name__}: {e}")
    import re
    m = re.search(r"(0\.0|0\.25|0\.5|0\.75|1\.0|0|1)", text)
    if not m:
        return (0.0, f"judge produced no parsable score: {text[:60]!r}")
    val = float(m.group(1))
    return (val, f"judge={val} raw={text[:40]!r}")


async def _run_one(
    client: AsyncOpenAI,
    model: str,
    judge_model: str,
    task: dict,
    sem: asyncio.Semaphore,
) -> dict:
    async with sem:
        t0 = time.time()
        messages = []
        if "system" in task:
            messages.append({"role": "system", "content": task["system"]})
        messages.append({"role": "user", "content": task["prompt"]})

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=task.get("max_tokens", 512),
                temperature=task.get("temperature", 0.0),
            )
            msg = resp.choices[0].message
            text = msg.content or ""
            # Many local servers (llama-swap, vLLM thinking variants) return
            # the chain-of-thought in `reasoning_content` and only the final
            # answer in `content`. Keep them separate so scoring sees just
            # the final answer, but log thinking length for diagnostics.
            reasoning_text = getattr(msg, "reasoning_content", None) or ""
            if not reasoning_text:
                extra = getattr(msg, "model_extra", None) or {}
                reasoning_text = extra.get("reasoning_content", "") or ""
            usage = resp.usage
            usage_dict = {
                "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            }
            details = getattr(usage, "completion_tokens_details", None)
            usage_dict["reasoning_tokens"] = getattr(details, "reasoning_tokens", 0) or 0 if details else 0
            if not usage_dict["reasoning_tokens"] and reasoning_text:
                usage_dict["reasoning_tokens"] = max(1, len(reasoning_text) // 4)
            err = None
        except APIError as e:
            text = ""
            usage_dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
            err = f"{type(e).__name__}: {str(e)[:200]}"
        except Exception as e:
            text = ""
            usage_dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
            err = f"{type(e).__name__}: {str(e)[:200]}"

        if err:
            return {
                "id": task["id"], "category": task["category"],
                "score": 0.0, "explanation": err,
                "elapsed": time.time() - t0,
                "response": "", "reasoning": "", "error": err, **usage_dict,
            }

        scoring_cfg = task["scoring"]
        if scoring_cfg["type"] == "judge":
            score_val, explanation = await _judge(client, judge_model, task, text)
        else:
            score_val, explanation = score_response(text, scoring_cfg)

        if not text and reasoning_text:
            explanation = (
                f"empty content — model used full budget on thinking "
                f"({len(reasoning_text)} reasoning chars). " + explanation
            )

        return {
            "id": task["id"], "category": task["category"],
            "score": float(score_val), "explanation": explanation,
            "elapsed": time.time() - t0,
            "response": text, "reasoning": reasoning_text,
            "error": None, **usage_dict,
        }


async def _run_all(
    model: str,
    judge_model: str,
    base_url: str,
    api_key: str,
    tasks: list[dict],
    parallel: int,
    rounds: int,
    log_dir: Path,
    quiet: bool,
) -> list[dict]:
    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=600, max_retries=1)
    sem = asyncio.Semaphore(parallel)

    jobs = [(rnd, t) for rnd in range(1, rounds + 1) for t in tasks]
    coros = [_run_one(client, model, judge_model, t, sem) for _, t in jobs]

    results: list[dict] = []
    for i, fut in enumerate(asyncio.as_completed(coros), 1):
        r = await fut
        results.append(r)
        if not quiet:
            status = "ok" if r["error"] is None else "ERR"
            print(
                f"  [{i:>3}/{len(jobs)}] {r['category']:<22} {r['id']:<26} "
                f"score={r['score']:.2f}  tok={_fmt(r['total_tokens']):>6}  "
                f"{r['elapsed']:>5.1f}s  [{status}]  {r['explanation'][:60]}",
                flush=True,
            )
        out = log_dir / f"{r['id']}.json"
        out.write_text(json.dumps(r, indent=2))
    await client.close()
    return results


def _report(results: list[dict], categories_present: list[str]) -> str:
    by_cat: dict[str, list[dict]] = {c: [] for c in categories_present}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    lines: list[str] = []
    w = 96
    lines.append("")
    lines.append("  sanity-bench results")
    lines.append("  " + "─" * w)
    lines.append(f"  {'Category':<22} {'Avg':>6} {'N':>4} {'Input':>9} {'Output':>9} {'Reason':>9} {'Total':>9} {'Wall':>7}")
    lines.append("  " + "─" * w)

    grand = {"score": 0.0, "n": 0, "input": 0, "output": 0, "reason": 0, "total": 0, "wall": 0.0}
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        n = len(rs)
        if n == 0:
            continue
        avg = sum(r["score"] for r in rs) / n
        inp = sum(r["input_tokens"] for r in rs)
        out = sum(r["output_tokens"] for r in rs)
        rea = sum(r["reasoning_tokens"] for r in rs)
        tot = sum(r["total_tokens"] for r in rs)
        wall = sum(r["elapsed"] for r in rs)
        lines.append(
            f"  {cat:<22} {avg:>6.3f} {n:>4} {_fmt(inp):>9} {_fmt(out):>9} {_fmt(rea):>9} {_fmt(tot):>9} {wall:>6.1f}s"
        )
        grand["score"] += avg
        grand["n"] += 1
        grand["input"] += inp
        grand["output"] += out
        grand["reason"] += rea
        grand["total"] += tot
        grand["wall"] += wall

    if grand["n"]:
        overall = grand["score"] / grand["n"]
        lines.append("  " + "─" * w)
        lines.append(
            f"  {'OVERALL (mean of cats)':<22} {overall:>6.3f} {grand['n']:>4} "
            f"{_fmt(grand['input']):>9} {_fmt(grand['output']):>9} {_fmt(grand['reason']):>9} {_fmt(grand['total']):>9} {grand['wall']:>6.1f}s"
        )
    lines.append("")
    return "\n".join(lines)


def _env_credentials() -> tuple[str, str]:
    base_url = os.environ.get("LOCAL_BASE_URL", "")
    api_key = os.environ.get("LOCAL_API_KEY", "")
    if not base_url or not api_key:
        env_file = ROOT.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if "=" not in line or line.startswith("#"):
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k == "LOCAL_BASE_URL" and not base_url:
                    base_url = v
                if k == "LOCAL_API_KEY" and not api_key:
                    api_key = v
    return base_url, api_key


def main() -> None:
    p = argparse.ArgumentParser(description="sanity-bench runner")
    p.add_argument("--model", required=True, help="Model name (as the OpenAI-compat server expects it)")
    p.add_argument("--judge-model", default=None, help="Model used for LLM-as-judge tasks (default: --model)")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible endpoint (overrides $LOCAL_BASE_URL)")
    p.add_argument("--api-key", default=None, help="API key (overrides $LOCAL_API_KEY)")
    p.add_argument("--categories", default="", help="Comma-separated category filter")
    p.add_argument("--tasks", default="", help="Comma-separated task ID filter")
    p.add_argument("--rounds", type=int, default=1, help="Repeat each task N times")
    p.add_argument("--parallel", type=int, default=4, help="Max concurrent in-flight requests")
    p.add_argument("--log-dir", default=None, help="Sidecar + report destination")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    base_url = args.base_url or _env_credentials()[0]
    api_key = args.api_key or _env_credentials()[1]
    if not base_url or not api_key:
        raise SystemExit("Missing base URL or API key. Set --base-url/--api-key or LOCAL_BASE_URL/LOCAL_API_KEY.")

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] or None
    task_ids = [t.strip() for t in args.tasks.split(",") if t.strip()] or None
    tasks = _load_tasks(cats, task_ids)
    if not tasks:
        raise SystemExit("No tasks matched the filters.")

    log_dir = Path(args.log_dir) if args.log_dir else DEFAULT_LOG_DIR / args.model
    log_dir.mkdir(parents=True, exist_ok=True)

    judge_model = args.judge_model or args.model

    if not args.quiet:
        cats_in = sorted({t["category"] for t in tasks})
        print(f"\n  sanity-bench: {len(tasks)} tasks x {args.rounds} round(s) -> {args.parallel} parallel")
        print(f"  Model:     {args.model}")
        print(f"  Judge:     {judge_model}")
        print(f"  Endpoint:  {base_url}")
        print(f"  Cats:      {', '.join(cats_in)}")
        print(f"  Log dir:   {log_dir}\n")

    t0 = time.time()
    results = asyncio.run(_run_all(
        model=args.model, judge_model=judge_model,
        base_url=base_url, api_key=api_key,
        tasks=tasks, parallel=args.parallel, rounds=args.rounds,
        log_dir=log_dir, quiet=args.quiet,
    ))
    elapsed = time.time() - t0

    cats_present = sorted({t["category"] for t in tasks})
    report = _report(results, cats_present)
    print(report)
    print(f"  Wall:      {elapsed:.1f}s")

    (log_dir / "report.txt").write_text(report + f"\n  Wall: {elapsed:.1f}s\n")
    (log_dir / "results.json").write_text(json.dumps(results, indent=2))
    print(f"  Report:    {log_dir / 'report.txt'}")
    print(f"  Results:   {log_dir / 'results.json'}\n")


if __name__ == "__main__":
    main()
