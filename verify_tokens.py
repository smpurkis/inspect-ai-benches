#!/usr/bin/env python3
"""Verify token usage tracking in .eval files.

Parses an .eval zip and compares header totals vs per-sample sums
to confirm inspect-ai is tracking tokens correctly.

Usage:
    uv run python verify_tokens.py logs/token_debug/*.eval
    uv run python verify_tokens.py logs/bench/gpt-5/pokemon-battle-fix/round_01/*.eval
"""

import json
import sys
import zipfile
from pathlib import Path


def analyze_eval(eval_path: Path) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {eval_path.name}")
    print(f"{'=' * 70}")

    with zipfile.ZipFile(eval_path, "r") as zf:
        header = json.loads(zf.read("header.json"))

        header_usage = header.get("stats", {}).get("model_usage", {})
        header_input = sum(u.get("input_tokens", 0) for u in header_usage.values())
        header_output = sum(u.get("output_tokens", 0) for u in header_usage.values())
        header_total = sum(u.get("total_tokens", 0) for u in header_usage.values())
        header_cache_read = sum(u.get("input_tokens_cache_read", 0) for u in header_usage.values())

        print(f"\n  HEADER (inspect total)")
        print(f"    input:      {header_input:>12,}")
        print(f"    output:     {header_output:>12,}")
        print(f"    total:      {header_total:>12,}")
        print(f"    cache_read: {header_cache_read:>12,}")

        dataset_samples = header.get("eval", {}).get("dataset", {}).get("samples", "?")

        try:
            summaries = json.loads(zf.read("summaries.json"))
        except KeyError:
            summaries = []

        print(f"\n  PER-SAMPLE BREAKDOWN ({len(summaries)}/{dataset_samples} completed)")
        print(f"  {'Sample':<42} {'Input':>10} {'Output':>8} {'Total':>10} {'Cache':>10}")
        print(f"  {'-' * 80}")

        sum_input = sum_output = sum_total = sum_cache = 0
        for s in summaries:
            name = s.get("id", "unknown")
            for _model, usage in s.get("model_usage", {}).items():
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                tot = usage.get("total_tokens", 0)
                cache = usage.get("input_tokens_cache_read", 0)
                sum_input += inp
                sum_output += out
                sum_total += tot
                sum_cache += cache
                print(f"  {name:<42} {inp:>10,} {out:>8,} {tot:>10,} {cache:>10,}")

        print(f"  {'-' * 80}")
        print(f"  {'SUM':<42} {sum_input:>10,} {sum_output:>8,} {sum_total:>10,} {sum_cache:>10,}")

        print(f"\n  COMPARISON")
        print(f"    Header total tokens:  {header_total:>12,}")
        print(f"    Sum of samples:       {sum_total:>12,}")
        diff = header_total - sum_total
        if diff == 0:
            print(f"    Match: EXACT")
        else:
            pct = (diff / header_total * 100) if header_total else 0
            print(f"    Difference:           {diff:>12,}  ({pct:.1f}% unattributed)")
            if len(summaries) < (dataset_samples if isinstance(dataset_samples, int) else 0):
                print(f"    NOTE: {dataset_samples - len(summaries)} samples didn't complete — their tokens are in header but not in summaries")

        sample_files = [n for n in zf.namelist() if n.startswith("samples/")]
        if sample_files and len(summaries) == 1:
            data = json.loads(zf.read(sample_files[0]))
            msgs = data.get("messages", [])
            assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
            tool_msgs = [m for m in msgs if m.get("role") == "tool"]
            print(f"\n  MESSAGE STATS (single sample)")
            print(f"    Total messages:     {len(msgs)}")
            print(f"    Assistant messages:  {len(assistant_msgs)}  (= generate calls)")
            print(f"    Tool responses:     {len(tool_msgs)}")
            if assistant_msgs:
                avg_input = sum_input / len(assistant_msgs)
                print(f"    Avg input/call:     {avg_input:,.0f}")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python verify_tokens.py <path_to.eval> [...]")
        sys.exit(1)

    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_file() and path.suffix == ".eval":
            analyze_eval(path)
        elif path.is_dir():
            for f in sorted(path.rglob("*.eval")):
                analyze_eval(f)
        else:
            print(f"Skipping {arg} (not an .eval file)")


if __name__ == "__main__":
    main()
