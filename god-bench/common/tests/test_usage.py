from __future__ import annotations

from math import isclose, sqrt

from usage import USAGE_SCHEMA_VERSION, UsageEvent, UsageTrace, efficiency_score


def _event(**overrides) -> UsageEvent:
    values = {
        "turn": 2,
        "tool": "run_public_tests",
        "normalized_command": "pytest -q /app/files/tests_public.py",
        "action_class": "public_test",
        "tool_cost": 5,
        "input_chars": 44,
        "output_chars": 120,
        "read_bytes": 0,
        "editable_fingerprint_before": "abc",
        "editable_fingerprint_after": "abc",
        "no_progress": False,
        "elapsed_seconds": 1.25,
    }
    values.update(overrides)
    return UsageEvent(**values)


def test_event_and_trace_json_round_trip_with_schema_version() -> None:
    event = _event(observed_path="spec/semantics.md", relevant=True)
    assert UsageEvent.from_json(event.to_json()) == event
    assert event.as_dict()["class"] == "public_test"
    assert event.as_dict()["schema_version"] == USAGE_SCHEMA_VERSION

    trace = UsageTrace(
        events=[event, _event(tool_cost=8, output_chars=30, no_progress=True)],
        model_input_tokens=800,
        model_output_tokens=200,
        benchmark_boilerplate_tokens=50,
        task_text_tokens=25,
        elapsed_seconds=4.5,
    )
    restored = UsageTrace.from_json(trace.to_json())

    assert restored.events == trace.events
    assert restored.model_tokens == 1000
    assert restored.weighted_tool_cost == 13
    assert restored.tool_output_chars == 150
    assert restored.no_progress_retries == 1
    assert restored.as_dict()["tool_calls"] == 2
    assert restored.unique_files_opened == 1
    assert restored.relevant_files_opened == 1
    assert restored.retrieval_precision == 1.0


def test_provider_billed_tokens_do_not_double_count_tool_output() -> None:
    trace = UsageTrace(
        events=[_event(output_chars=100_000)],
        model_input_tokens=10,
        model_output_tokens=5,
    )
    assert trace.model_tokens == 15
    assert trace.tool_output_chars == 100_000


def test_retrieval_metrics_are_unique_and_non_context_traces_are_null() -> None:
    trace = UsageTrace(
        events=[
            _event(observed_path="spec/semantics.md", relevant=True),
            _event(observed_path="spec/semantics.md", relevant=True),
            _event(observed_path="src/main.py", relevant=False),
        ]
    )
    assert trace.unique_files_opened == 2
    assert trace.relevant_files_opened == 1
    assert trace.retrieval_precision == 0.5

    plain = UsageTrace(events=[_event(observed_path="src/main.py")])
    assert plain.unique_files_opened is None
    assert plain.relevant_files_opened is None
    assert plain.retrieval_precision is None
    assert plain.as_dict()["retrieval_precision"] is None


def test_efficiency_is_correctness_gated() -> None:
    assert efficiency_score(
        functional_pass=False,
        model_tokens=1,
        token_budget=100,
        weighted_tool_cost=1,
        tool_cost_budget=10,
        no_progress_retries=0,
    ) == 0.0


def test_under_budget_correct_attempt_scores_one() -> None:
    assert efficiency_score(
        functional_pass=True,
        model_tokens=100,
        token_budget=100,
        weighted_tool_cost=10,
        tool_cost_budget=10,
        no_progress_retries=0,
    ) == 1.0
    assert efficiency_score(
        functional_pass=True,
        model_tokens=0,
        token_budget=100,
        weighted_tool_cost=0,
        tool_cost_budget=10,
        no_progress_retries=0,
    ) == 1.0


def test_over_budget_and_retry_factors_match_formula() -> None:
    score = efficiency_score(
        functional_pass=True,
        model_tokens=400,
        token_budget=100,
        weighted_tool_cost=40,
        tool_cost_budget=10,
        no_progress_retries=3,
        retry_allowance=1,
    )
    expected = sqrt(100 / 400) * sqrt(10 / 40) * (1 / (1 + 0.05 * 2))
    assert isclose(score, expected)
