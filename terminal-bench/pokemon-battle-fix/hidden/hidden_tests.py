#!/usr/bin/env python3
"""Hidden tests: battle mechanics with variant scenarios."""

import json
import sys
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
FILES_BASE = HIDDEN_BASE.parent / "files"
sys.path.insert(0, str(FILES_BASE))

from emulator.game_engine import load_savestate, replay_actions, state_to_dict
from emulator.types import GameScreen


def load_hidden_ref(name):
    with open(HIDDEN_BASE / "reference" / name) as f:
        return json.load(f)


def test_hidden_battle_different_lead():
    """Hidden scenario with Sceptile lead instead of Blaziken."""
    ref = load_hidden_ref("battle_hidden_01_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_01.json"))

    assert state.player_party[0].species == "Sceptile"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won with Sceptile lead"
    assert result["whiteout"] is False

    # Verify damage calculation is correct (catches dual-type effectiveness bug)
    assert result["player_party"][0]["hp"] == ref["player_hp"], (
        f"Player HP should be {ref['player_hp']} but got {result['player_party'][0]['hp']} "
        f"— likely a type effectiveness calculation error"
    )


def test_hidden_battle_low_hp_start():
    """Player starts with reduced HP and must still win."""
    ref = load_hidden_ref("battle_hidden_02_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_02.json"))

    assert state.player_party[0].hp == 25, "Player should start with low HP"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["whiteout"] is False, "Player should not whiteout"
    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    )


def test_hidden_battle_status_condition():
    """Enemy starts with poison status; poison damage should apply each turn."""
    ref = load_hidden_ref("battle_hidden_03_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_03.json"))

    assert state.enemy_trainer.party[0].status == "poison"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    )


def test_hidden_battle_stab_second_type():
    """Hidden scenario where STAB on a secondary type is required to OHKO."""
    ref = load_hidden_ref("battle_hidden_04_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_04.json"))

    assert state.player_party[0].species == "Blaziken"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won (STAB must apply for secondary type moves)"
    assert result["whiteout"] is False
    assert result["player_party"][0]["hp"] == ref["player_hp"], (
        f"Player HP should be {ref['player_hp']} but got {result['player_party'][0]['hp']}"
    )


def test_hidden_battle_action_efficiency():
    """Solutions should be within 80% of optimal action count."""
    for i in range(1, 5):
        ref = load_hidden_ref(f"battle_hidden_{i:02d}_result.json")
        # Each battle should complete in a reasonable number of actions
        assert ref["action_count"] <= 48, (
            f"Hidden battle {i} uses {ref['action_count']} actions, exceeds 80% of 60 cap"
        )


def test_hidden_battle_no_whiteout():
    """Player never faints in any hidden scenario."""
    for i in range(1, 5):
        ref = load_hidden_ref(f"battle_hidden_{i:02d}_result.json")
        state = load_savestate(
            str(HIDDEN_BASE / "savestates" / f"battle_hidden_{i:02d}.json")
        )
        state = replay_actions(state, ref["actions"])
        result = state_to_dict(state)
        assert result["whiteout"] is False, f"Hidden battle {i}: player should not whiteout"


def test_hidden_battle_deterministic():
    """All hidden scenarios replay identically on two runs."""
    for i in range(1, 5):
        ref = load_hidden_ref(f"battle_hidden_{i:02d}_result.json")
        save_path = str(HIDDEN_BASE / "savestates" / f"battle_hidden_{i:02d}.json")

        s1 = load_savestate(save_path)
        s1 = replay_actions(s1, ref["actions"])
        r1 = state_to_dict(s1)

        s2 = load_savestate(save_path)
        s2 = replay_actions(s2, ref["actions"])
        r2 = state_to_dict(s2)

        assert r1 == r2, f"Hidden battle {i}: replays should be identical"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
