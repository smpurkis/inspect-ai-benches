from __future__ import annotations

import json

from common.reporting import build_report, load_trials


def _trial(model: str, task: str, solved: bool, tokens: int, efficiency: float):
    return {
        "task_name": task,
        "started_at": "2026-07-23T10:00:00+00:00",
        "finished_at": "2026-07-23T10:00:10+00:00",
        "agent_info": {"model_info": {"provider": "openai", "name": model}},
        "agent_result": {
            "metadata": {
                "usage": {
                    "within_budget": solved,
                    "trace": {"retrieval_precision": 0.5},
                }
            }
        },
        "verifier_result": {
            "rewards": {
                "correctness": int(solved),
                "efficiency": efficiency,
                "model_tokens": tokens,
                "weighted_tool_cost": 4,
                "within_budget": int(solved),
                "usage_valid": 1,
            }
        },
    }


def test_load_trials_reads_native_harbor_trial_results(tmp_path):
    trial_dir = tmp_path / "job" / "trial"
    trial_dir.mkdir(parents=True)
    (trial_dir / "result.json").write_text(json.dumps(_trial("a", "task", True, 10, 1.0)))
    (tmp_path / "job" / "result.json").write_text("{}")

    assert [trial["task_name"] for trial in load_trials(tmp_path)] == ["task"]


def test_report_ranks_correctness_before_efficiency():
    report = build_report(
        [
            _trial("capable", "a", True, 100, 0.5),
            _trial("capable", "b", True, 200, 0.4),
            _trial("cheap-failure", "a", False, 1, 0.0),
        ]
    )

    capable = report.index("openai/capable")
    failure = report.index("openai/cheap-failure")
    assert capable < failure
    assert "50.0%" in report


def test_report_keeps_capability_but_excludes_invalid_efficiency_usage():
    trial = _trial("invalid-usage", "a", True, 1, 1.0)
    trial["verifier_result"]["rewards"]["usage_valid"] = 0

    report = build_report([trial])

    assert "1/1" in report
    assert "       0.000" in report
    assert "            n/a" in report
