from __future__ import annotations

from dataclasses import FrozenInstanceError
from time import monotonic

import pytest

from budget import BudgetConfig, BudgetState, load_contract


def test_defaults_are_finite_and_config_is_immutable(tmp_path) -> None:
    config = load_contract(tmp_path)

    assert config == BudgetConfig(
        max_agent_turns=24,
        max_weighted_tool_cost=44,
        max_public_test_runs=3,
        max_file_read_bytes=180_000,
        wall_clock_seconds=900,
        max_model_tokens=64_000,
    )
    with pytest.raises(FrozenInstanceError):
        config.max_agent_turns = 100  # type: ignore[misc]


def test_load_contract_overrides_only_declared_limits(tmp_path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "contract.toml").write_text(
        """
[task]
id = "example"

[limits]
max_agent_turns = 12
max_weighted_tool_cost = 20
max_public_test_runs = 2
max_file_read_bytes = 4096
wall_clock_seconds = 30
max_model_tokens = 8000
future_limit = 99
""",
        encoding="utf-8",
    )

    assert load_contract(tmp_path) == BudgetConfig(
        max_agent_turns=12,
        max_weighted_tool_cost=20,
        max_public_test_runs=2,
        max_file_read_bytes=4096,
        wall_clock_seconds=30,
        max_model_tokens=8000,
    )


@pytest.mark.parametrize("value", [0, -1])
def test_limits_must_be_positive(value) -> None:
    with pytest.raises(ValueError):
        BudgetConfig(max_agent_turns=value)


def test_limit_reached_is_exhausted_but_one_below_is_not() -> None:
    config = BudgetConfig(
        max_agent_turns=10,
        max_weighted_tool_cost=20,
        max_public_test_runs=3,
        max_file_read_bytes=100,
        wall_clock_seconds=50,
        max_model_tokens=1000,
    )
    below = BudgetState(
        config=config,
        turns=9,
        weighted_tool_cost=19,
        public_test_runs=2,
        file_read_bytes=99,
        model_tokens=999,
        started_at=100.0,
    )
    assert not below.exhausted(now=149.999)

    boundaries = (
        {"turns": 10},
        {"weighted_tool_cost": 20},
        {"public_test_runs": 3},
        {"file_read_bytes": 100},
        {"model_tokens": 1000},
    )
    for usage in boundaries:
        assert BudgetState(config=config, started_at=100.0, **usage).exhausted(now=100.0)
    assert BudgetState(config=config, started_at=100.0).exhausted(now=150.0)


def test_checkpoints_are_one_shot_and_finalization_stops_at_exhaustion() -> None:
    config = BudgetConfig(max_agent_turns=10)
    started_at = monotonic()
    state = BudgetState(config=config, started_at=started_at)

    state.turns = 4
    assert state.checkpoint(now=started_at) is None
    state.turns = 5
    assert state.checkpoint(now=started_at) == 50
    assert state.checkpoint(now=started_at) is None

    state.turns = 8
    assert state.checkpoint(now=started_at) == 80
    assert state.in_finalization_mode
    state.turns = 10
    assert state.exhausted(now=started_at)
    assert not state.in_finalization_mode


def test_jump_claims_highest_checkpoint_and_snapshot_is_json_compatible() -> None:
    state = BudgetState(
        config=BudgetConfig(max_weighted_tool_cost=10),
        weighted_tool_cost=8,
        no_progress_retries=1,
        started_at=20.0,
    )

    assert state.checkpoint(now=25.0) == 80
    snapshot = state.as_dict(now=25.0)
    assert snapshot["checkpoints_emitted"] == [50, 80]
    assert snapshot["elapsed_seconds"] == 5.0
    assert snapshot["weighted_tool_cost"] == 8
    assert snapshot["in_finalization_mode"] is True


def test_apply_rejects_negative_usage() -> None:
    state = BudgetState()
    state.apply(turns=1, weighted_tool_cost=5, model_tokens=100)
    assert (state.turns, state.weighted_tool_cost, state.model_tokens) == (1, 5, 100)
    with pytest.raises(ValueError):
        state.apply(file_read_bytes=-1)


def test_elapsed_can_be_frozen_before_verifier_work() -> None:
    state = BudgetState(started_at=100.0)
    assert state.freeze_elapsed(now=112.5) == 12.5
    assert state.elapsed(now=999.0) == 12.5
    assert state.as_dict(now=999.0)["elapsed_seconds"] == 12.5
