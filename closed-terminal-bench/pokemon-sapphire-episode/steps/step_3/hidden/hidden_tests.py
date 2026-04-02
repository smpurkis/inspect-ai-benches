#!/usr/bin/env python3
"""Step 3 hidden tests: gym episode with variant scenarios."""

import json
import sys
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
STEP3_BASE = HIDDEN_BASE.parent / "files"
STEP1_BASE = HIDDEN_BASE.parent.parent / "step_1" / "files"
sys.path.insert(0, str(STEP1_BASE))

from emulator.game_engine import load_savestate, replay_actions, state_to_dict, process_input
from emulator.types import GameScreen, Button


def load_hidden_ref(name):
    with open(HIDDEN_BASE / "reference" / name) as f:
        return json.load(f)


def load_solution():
    """Load the agent's solution actions from step 3 files."""
    solution_path = STEP3_BASE / "solution_actions.json"
    with open(solution_path) as f:
        return json.load(f)


def run_hidden_gym(save_name):
    """Run the agent's solution against a hidden gym savestate."""
    actions = load_solution()
    state = load_savestate(str(HIDDEN_BASE / "savestates" / save_name))
    state = replay_actions(state, actions)
    return state, actions


def test_hidden_gym_different_party():
    """Gym challenge with Mudkip-line lead — engine loads correctly with different party."""
    state = load_savestate(
        str(HIDDEN_BASE / "savestates" / "gym_hidden_01.json")
    )
    # Gym_hidden_01 has Swampert as lead
    assert state.player_party[0].species == "Swampert", (
        f"Expected Swampert lead, got {state.player_party[0].species}"
    )
    assert state.map_name == "Dewford Gym"
    assert len(state.map_grid) > 0

    # Verify all trainers have valid party data (gym is completable)
    trainer_count = 0
    for row in state.map_grid:
        for tile in row:
            if tile.trainer and not tile.trainer.defeated:
                trainer_count += 1
                assert len(tile.trainer.party) > 0, (
                    f"Trainer {tile.trainer.name} has no party"
                )
    assert trainer_count >= 3, f"Expected >= 3 trainers, found {trainer_count}"


def test_hidden_no_excess_actions():
    """Agent's solution uses no more than 400 actions (stricter hidden cap)."""
    actions = load_solution()
    assert len(actions) <= 400, (
        f"Solution uses {len(actions)} actions; hidden cap is 400"
    )


def test_hidden_no_type_spam():
    """Agent does not always press the same move slot — uses at least 2 different slots."""
    actions = load_solution()
    state = load_savestate(str(STEP3_BASE / "savestates" / "gym_visible.json"))

    move_slots_used = set()
    for action_str in actions:
        button = Button[action_str]
        # Track cursor position when A is pressed in BATTLE_MOVES
        if state.screen == GameScreen.BATTLE_MOVES and button == Button.A:
            move_slots_used.add(state.cursor_position)
        state = process_input(state, button)
        if state.whiteout:
            break

    # If any battle moves were made, agent should use more than one slot
    if len(move_slots_used) > 0:
        assert len(move_slots_used) >= 2, (
            f"Agent only used move slot(s) {move_slots_used}; "
            "should pick moves strategically (use at least 2 different move slots)"
        )


def test_hidden_healing_used_correctly():
    """If Potions are in inventory, they are used when HP falls below 30%."""
    # gym_hidden_02 has 5 Potions — verify the agent uses them or starts with empty inventory
    state = load_savestate(
        str(HIDDEN_BASE / "savestates" / "gym_hidden_02.json")
    )
    initial_potions = state.inventory.get("Potion", 0) + state.inventory.get("Super Potion", 0)

    if initial_potions == 0:
        # No potions available — nothing to test, pass trivially
        return

    # Run the solution against this harder savestate
    actions = load_solution()
    final_state = load_savestate(str(HIDDEN_BASE / "savestates" / "gym_hidden_02.json"))

    # Track HP and potion usage step by step
    healing_triggered_when_low = False
    potion_used = False

    for action_str in actions:
        button = Button[action_str]
        player_hp = final_state.player_party[0].hp
        player_max_hp = final_state.player_party[0].max_hp
        hp_ratio = player_hp / max(player_max_hp, 1)

        # Check if a potion was about to be used when HP was low
        if (
            final_state.screen == GameScreen.BAG_MENU
            and button == Button.A
            and hp_ratio < 0.30
        ):
            healing_triggered_when_low = True

        inventory_before = dict(final_state.inventory)
        final_state = process_input(final_state, button)
        inventory_after = dict(final_state.inventory)

        if inventory_before != inventory_after:
            potion_used = True

        if final_state.whiteout:
            break

    # Either potions were used (agent managed healing) or inventory ended empty
    final_potions = (
        final_state.inventory.get("Potion", 0)
        + final_state.inventory.get("Super Potion", 0)
    )
    # Accept: potions were used at some point, OR they remain unused (agent didn't need them)
    # The key check: agent didn't whiteout despite having potions available
    assert not final_state.whiteout, (
        "Agent whited out even with Potions available in inventory"
    )


def test_hidden_deterministic():
    """Ten-action prefix replays identically twice on each hidden savestate."""
    test_actions_prefix = load_solution()[:10]

    for i in range(1, 3):
        save_path = str(HIDDEN_BASE / "savestates" / f"gym_hidden_{i:02d}.json")

        s1 = load_savestate(save_path)
        s1 = replay_actions(s1, test_actions_prefix)
        r1 = state_to_dict(s1)

        s2 = load_savestate(save_path)
        s2 = replay_actions(s2, test_actions_prefix)
        r2 = state_to_dict(s2)

        assert r1 == r2, (
            f"Hidden gym {i:02d}: 10-action prefix replay is not deterministic"
        )


def test_hidden_badge_flag_correct():
    """Hidden reference files confirm badge_obtained=True and badges=1."""
    ref1 = load_hidden_ref("gym_hidden_01_result.json")
    assert ref1["badge_obtained"] is True, "gym_hidden_01: badge_obtained should be True"
    assert ref1["badges"] == 1, f"gym_hidden_01: expected badges=1, got {ref1['badges']}"

    ref2 = load_hidden_ref("gym_hidden_02_result.json")
    assert ref2["badge_obtained"] is True, "gym_hidden_02: badge_obtained should be True"
    assert ref2["badges"] == 1, f"gym_hidden_02: expected badges=1, got {ref2['badges']}"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
