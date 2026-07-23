"""Native Harbor result loading and correctness-first GOD-Bench reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable


def load_trials(jobs_dir: Path) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    if not jobs_dir.exists():
        return trials
    for path in sorted(jobs_dir.glob("*/*/result.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and "task_name" in value:
            value["_result_path"] = str(path)
            trials.append(value)
    return trials


def _model(trial: dict[str, Any]) -> str:
    info = trial.get("agent_info", {}).get("model_info") or {}
    name = str(info.get("name") or "unknown")
    provider = info.get("provider")
    return f"{provider}/{name}" if provider else name


def _rewards(trial: dict[str, Any]) -> dict[str, int | float]:
    value = (trial.get("verifier_result") or {}).get("rewards") or {}
    return value if isinstance(value, dict) else {}


def _usage(trial: dict[str, Any]) -> dict[str, Any]:
    metadata = (trial.get("agent_result") or {}).get("metadata") or {}
    value = metadata.get("usage") or {}
    return value if isinstance(value, dict) else {}


def _elapsed(trial: dict[str, Any]) -> float | None:
    try:
        start = datetime.fromisoformat(trial["started_at"])
        finish = datetime.fromisoformat(trial["finished_at"])
        return max(0.0, (finish - start).total_seconds())
    except (KeyError, TypeError, ValueError):
        return None


def _fmt(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def build_report(trials: Iterable[dict[str, Any]]) -> str:
    rows = list(trials)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trial in rows:
        grouped[_model(trial)].append(trial)

    aggregates: list[dict[str, Any]] = []
    for model, attempts in grouped.items():
        solved = [trial for trial in attempts if _rewards(trial).get("correctness") == 1]
        valid_solved = [
            trial for trial in solved if _rewards(trial).get("usage_valid") == 1
        ]
        under_budget = [
            trial
            for trial in valid_solved
            if _rewards(trial).get("within_budget") == 1
        ]
        efficiencies = [
            float(_rewards(trial).get("efficiency", 0.0)) for trial in valid_solved
        ]
        tokens = [
            int(_rewards(trial).get("model_tokens", 0))
            for trial in valid_solved
        ]
        tool_costs = [
            int(_rewards(trial).get("weighted_tool_cost", 0))
            for trial in valid_solved
        ]
        elapsed = [
            value for trial in valid_solved if (value := _elapsed(trial)) is not None
        ]
        retrieval = []
        for trial in valid_solved:
            precision = (_usage(trial).get("trace") or {}).get("retrieval_precision")
            if isinstance(precision, (int, float)) and not isinstance(precision, bool):
                retrieval.append(float(precision))
        aggregates.append(
            {
                "model": model,
                "attempts": len(attempts),
                "solved": len(solved),
                "under_budget": len(under_budget),
                "efficiency": sum(efficiencies),
                "tokens": median(tokens) if tokens else None,
                "tool_cost": median(tool_costs) if tool_costs else None,
                "elapsed": median(elapsed) if elapsed else None,
                "retrieval": median(retrieval) if retrieval else None,
            }
        )
    aggregates.sort(
        key=lambda item: (
            -item["solved"],
            -item["under_budget"],
            -item["efficiency"],
            item["tokens"] if item["tokens"] is not None else float("inf"),
            item["tool_cost"] if item["tool_cost"] is not None else float("inf"),
            item["elapsed"] if item["elapsed"] is not None else float("inf"),
            item["model"],
        )
    )

    lines = [
        "GOD-Bench native Harbor results",
        "",
        "Rank  Model                                      Solved  Budgeted  Efficiency  Median tokens  Tool cost  Elapsed  Retrieval",
        "----  -----------------------------------------  ------  --------  ----------  -------------  ---------  -------  ---------",
    ]
    for rank, item in enumerate(aggregates, 1):
        retrieval = (
            "n/a" if item["retrieval"] is None else f"{100 * item['retrieval']:.1f}%"
        )
        lines.append(
            f"{rank:>4}  {item['model']:<41}  "
            f"{item['solved']:>3}/{item['attempts']:<2}  {item['under_budget']:>8}  "
            f"{item['efficiency']:>10.3f}  {_fmt(item['tokens'], 0):>13}  "
            f"{_fmt(item['tool_cost']):>9}  {_fmt(item['elapsed']):>7}  {retrieval:>9}"
        )
    return "\n".join(lines)


__all__ = ["build_report", "load_trials"]
