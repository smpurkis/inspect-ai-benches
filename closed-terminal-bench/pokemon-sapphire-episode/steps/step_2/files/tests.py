#!/usr/bin/env python3
"""Step 2 visible tests: trainer patrol and line-of-sight verification."""

import json
import sys
from pathlib import Path

STEP2_BASE = Path(__file__).resolve().parent
STEP1_BASE = STEP2_BASE.parent.parent / "step_1" / "files"
sys.path.insert(0, str(STEP1_BASE))

from emulator.game_engine import (
    load_savestate, replay_actions, state_to_dict, process_input,
    _check_trainer_vision, _update_trainer_patrol,
)
from emulator.types import GameScreen, Button, Direction

SAVESTATE = STEP2_BASE / "savestates" / "route_visible.json"
SOLUTION = STEP2_BASE / "solution_actions_step2.json"


def load_solution():
    with open(SOLUTION) as f:
        return json.load(f)


def test_overworld_loads():
    """Route savestate loads with map grid and patrol trainer."""
    state = load_savestate(str(SAVESTATE))
    assert state.screen == GameScreen.OVERWORLD
    assert state.map_name == "Route 106"
    assert len(state.map_grid) > 0, "Map grid should not be empty"
    assert len(state.map_grid[0]) > 0, "Map row should not be empty"
    assert state.player_position == (1, 6)
    # Patrol trainer must be present
    assert len(state.patrol_trainers) >= 1, "Should have at least one patrol trainer"
    jake = state.patrol_trainers[0]
    assert jake.name == "Youngster Jake"
    assert jake.facing == "DOWN"
    assert jake.vision_range == 3


def test_trainer_vision_triggers_battle():
    """Moving player directly into trainer's forward 3-tile vision cone triggers battle.

    With the patrol bug fixed and the vision bug fixed:
    - Youngster Jake is at [3,4] facing DOWN
    - His vision cone covers [3,5], [3,6], [3,7]
    - Moving player to [3,5] should trigger battle_active=True
    """
    state = load_savestate(str(SAVESTATE))
    # Place player directly below Jake (at [3,5]) to be in his DOWN cone
    # Jake faces DOWN: vision cone is tiles at (3,5), (3,6), (3,7)
    state.player_position = (3, 5)
    # Set player facing DOWN to match trainer facing (exercises fixed vision check)
    state.player_facing = Direction.DOWN

    # Make sure Jake's position is set correctly
    jake = state.patrol_trainers[0]
    jake.position = [3, 4]

    triggered = _check_trainer_vision(state)
    assert triggered is True, (
        "Vision check should trigger battle when player is in trainer's forward cone. "
        "Ensure _check_trainer_vision uses trainer.facing (not player facing)."
    )
    assert state.battle_active is True, "battle_active should be True after vision trigger"
    assert state.screen == GameScreen.BATTLE_MAIN


def test_blind_spot_allows_pass():
    """Approaching trainer from the side (not in vision cone) does NOT trigger battle.

    With the vision bug fixed, Jake faces DOWN — his cone is column 3 below him.
    A player standing to his side at [2,4] or [4,4] is NOT in the cone.
    """
    state = load_savestate(str(SAVESTATE))
    jake = state.patrol_trainers[0]
    jake.position = [3, 4]

    # Player to the side — not in Jake's DOWN-facing vision cone
    state.player_position = (2, 4)
    state.player_facing = Direction.RIGHT  # player facing right, irrelevant after fix

    triggered = _check_trainer_vision(state)
    assert triggered is False, (
        "Approaching from the side should NOT trigger battle. "
        "Trainer's DOWN cone covers column 3 below him, not column 2."
    )
    assert state.battle_active is False


def test_trainer_blocks_path_until_defeated():
    """Trainer's vision zone blocks the direct path; defeated trainer clears it."""
    state = load_savestate(str(SAVESTATE))
    jake = state.patrol_trainers[0]
    jake.position = [3, 4]

    # With Jake undefeated and player entering his cone, battle triggers
    state.player_position = (3, 6)
    state.player_facing = Direction.DOWN  # matches trainer facing for vision check
    triggered_undefeated = _check_trainer_vision(state)
    assert triggered_undefeated is True, "Undefeated trainer should block path via vision"

    # Now mark Jake as defeated
    state2 = load_savestate(str(SAVESTATE))
    jake2 = state2.patrol_trainers[0]
    jake2.position = [3, 4]
    jake2.defeated = True

    state2.player_position = (3, 6)
    state2.player_facing = Direction.DOWN
    triggered_defeated = _check_trainer_vision(state2)
    assert triggered_defeated is False, "Defeated trainer should no longer block path"


def test_action_count_under_cap():
    """Solution uses at most 200 actions."""
    actions = load_solution()
    assert len(actions) <= 200, (
        f"Action count {len(actions)} exceeds cap of 200"
    )


def test_deterministic_navigation():
    """Two replays of the solution produce identical final state."""
    actions = load_solution()

    s1 = load_savestate(str(SAVESTATE))
    s1 = replay_actions(s1, actions)
    r1 = state_to_dict(s1)

    s2 = load_savestate(str(SAVESTATE))
    s2 = replay_actions(s2, actions)
    r2 = state_to_dict(s2)

    assert r1 == r2, "Two replays should produce identical final state"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
