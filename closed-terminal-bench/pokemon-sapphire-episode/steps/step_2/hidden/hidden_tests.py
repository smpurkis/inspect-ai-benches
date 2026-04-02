#!/usr/bin/env python3
"""Step 2 hidden tests: patrol routes, vision mechanics, and route navigation variants."""

import json
import sys
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
STEP2_BASE = HIDDEN_BASE.parent / "files"
STEP1_BASE = HIDDEN_BASE.parent.parent / "step_1" / "files"
sys.path.insert(0, str(STEP1_BASE))

from emulator.game_engine import (
    load_savestate, replay_actions, state_to_dict, process_input,
    _check_trainer_vision, _update_trainer_patrol,
)
from emulator.types import GameScreen, Button, Direction


def load_hidden_ref(name):
    with open(HIDDEN_BASE / "reference" / name) as f:
        return json.load(f)


def test_hidden_route_different_start():
    """Hidden scenario: player starts at a different position ([1,1]) and must reach exit."""
    ref = load_hidden_ref("route_hidden_01_result.json")
    state = load_savestate(
        str(HIDDEN_BASE / "savestates" / "route_hidden_01.json")
    )
    assert state.player_position == (1, 1), (
        f"Hidden route 01 should start at (1,1), got {state.player_position}"
    )
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["flags"].get("reached_exit") is True, "Should reach exit tile"
    assert result["flags"].get("talked_to_Fisherman") is True, (
        "Should have talked to Fisherman NPC"
    )


def test_hidden_trainer_defeated_clears_path():
    """After defeating a patrol trainer, the path through their zone is clear."""
    # Use visible savestate's patrol trainer (Youngster Jake) for this check
    state = load_savestate(str(STEP2_BASE / "savestates" / "route_visible.json"))
    jake = state.patrol_trainers[0]
    jake.position = [3, 4]

    # Before defeating: player in Jake's DOWN cone triggers battle
    state.player_position = (3, 5)
    state.player_facing = Direction.DOWN
    triggered = _check_trainer_vision(state)
    assert triggered is True, "Jake should spot player before being defeated"

    # Mark Jake as defeated and reload a fresh state
    state2 = load_savestate(str(STEP2_BASE / "savestates" / "route_visible.json"))
    jake2 = state2.patrol_trainers[0]
    jake2.position = [3, 4]
    jake2.defeated = True

    # After defeating: same position no longer triggers battle
    state2.player_position = (3, 5)
    state2.player_facing = Direction.DOWN
    triggered2 = _check_trainer_vision(state2)
    assert triggered2 is False, (
        "Defeated trainer should not trigger vision battle — path is now clear"
    )


def test_hidden_patrol_path_updates():
    """Trainer position advances along patrol route with each engine step."""
    state = load_savestate(str(STEP2_BASE / "savestates" / "route_visible.json"))
    jake = state.patrol_trainers[0]

    # Record starting patrol index and position
    start_index = jake.patrol_index  # 0
    initial_pos = list(jake.position) if jake.position else list(jake.patrol_route[0])

    # Trigger one patrol update
    _update_trainer_patrol(state)
    after_one = jake.patrol_index

    # Trigger another update
    _update_trainer_patrol(state)
    after_two = jake.patrol_index

    # Index should advance each call (with the bug fixed, index advances after move)
    assert after_one != start_index or after_two != after_one, (
        "Patrol index should change after _update_trainer_patrol calls"
    )

    # After enough updates, trainer should cycle back to start of route
    route_len = len(jake.patrol_route)
    for _ in range(route_len * 2):
        _update_trainer_patrol(state)
    # Index must stay within route bounds
    assert 0 <= jake.patrol_index < route_len, (
        f"Patrol index {jake.patrol_index} out of bounds [0, {route_len})"
    )


def test_hidden_no_out_of_bounds():
    """Player never leaves valid map bounds during navigation in any hidden scenario."""
    for i in range(1, 4):
        ref = load_hidden_ref(f"route_hidden_{i:02d}_result.json")
        save_path = str(HIDDEN_BASE / "savestates" / f"route_hidden_{i:02d}.json")
        state = load_savestate(save_path)

        for action_str in ref["actions"]:
            button = Button[action_str]
            state = process_input(state, button)
            px, py = state.player_position
            if len(state.map_grid) > 0:
                assert 0 <= py < len(state.map_grid), (
                    f"Route hidden {i:02d}: player Y={py} out of bounds"
                )
                assert 0 <= px < len(state.map_grid[0]), (
                    f"Route hidden {i:02d}: player X={px} out of bounds"
                )


def test_hidden_flag_set():
    """Story flags are set after NPC interaction in hidden scenarios."""
    # Variant 1: talked_to_Fisherman (route_hidden_01)
    ref1 = load_hidden_ref("route_hidden_01_result.json")
    state1 = load_savestate(
        str(HIDDEN_BASE / "savestates" / "route_hidden_01.json")
    )
    state1 = replay_actions(state1, ref1["actions"])
    result1 = state_to_dict(state1)
    assert result1["flags"].get("talked_to_Fisherman") is True, (
        "talked_to_Fisherman flag should be set after interaction"
    )

    # Variant 3: talked_to_Ranger (route_hidden_03)
    ref3 = load_hidden_ref("route_hidden_03_result.json")
    state3 = load_savestate(
        str(HIDDEN_BASE / "savestates" / "route_hidden_03.json")
    )
    state3 = replay_actions(state3, ref3["actions"])
    result3 = state_to_dict(state3)
    assert result3["flags"].get("talked_to_Ranger") is True, (
        "talked_to_Ranger flag should be set after interaction"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
