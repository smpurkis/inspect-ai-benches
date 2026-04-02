#!/usr/bin/env python3
"""Step 3 visible tests: full gym episode verification."""

import json
import sys
from pathlib import Path

STEP3_BASE = Path(__file__).resolve().parent
STEP1_BASE = STEP3_BASE.parent.parent / "step_1" / "files"
sys.path.insert(0, str(STEP1_BASE))

from emulator.game_engine import load_savestate, replay_actions, state_to_dict
from emulator.types import GameScreen

SAVESTATE = STEP3_BASE / "savestates" / "gym_visible.json"
SOLUTION = STEP3_BASE / "solution_actions.json"


def load_solution():
    with open(SOLUTION) as f:
        return json.load(f)


def run_gym():
    actions = load_solution()
    state = load_savestate(str(SAVESTATE))
    state = replay_actions(state, actions)
    return state, actions


def test_gym_loads():
    """Gym savestate loads correctly with map and overworld screen."""
    state = load_savestate(str(SAVESTATE))
    assert state.screen == GameScreen.OVERWORLD
    assert state.map_name == "Dewford Gym"
    assert len(state.map_grid) > 0, "Map grid should not be empty"


def test_gym_leader_defeated():
    """Leader Brawly is among defeated trainers after action sequence."""
    state, _ = run_gym()

    defeated_names = set()
    for row in state.map_grid:
        for tile in row:
            if tile.trainer and tile.trainer.defeated:
                defeated_names.add(tile.trainer.name)

    assert "Leader Brawly" in defeated_names, (
        f"Leader Brawly should be defeated. Defeated trainers: {defeated_names}"
    )


def test_badge_obtained():
    """Badge is awarded after defeating the gym leader."""
    state, _ = run_gym()
    result = state_to_dict(state)

    assert result["badges"] >= 1 or result["flags"].get("badge_obtained") is True, (
        "Badge should be obtained after defeating the gym leader"
    )


def test_no_whiteout():
    """Player never loses all Pokemon during the gym run."""
    state, _ = run_gym()
    result = state_to_dict(state)
    assert result["whiteout"] is False, "Player must not white out"


def test_map_exploration_required():
    """Solution file exists and begins with exploration before any A press."""
    actions = load_solution()
    assert len(actions) > 0, "solution_actions.json must not be empty"

    direction_buttons = {"UP", "DOWN", "LEFT", "RIGHT"}
    first_20 = actions[:20]

    # Verify there is at least one directional move before the first A press
    first_a_index = None
    for i, action in enumerate(first_20):
        if action == "A":
            first_a_index = i
            break

    has_direction_before_a = any(
        action in direction_buttons
        for action in (first_20[:first_a_index] if first_a_index is not None else first_20)
    )

    assert has_direction_before_a, (
        "The first 20 actions must include at least one directional move "
        "(UP/DOWN/LEFT/RIGHT) before the first A press. "
        "Explore the gym before immediately pressing A."
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
