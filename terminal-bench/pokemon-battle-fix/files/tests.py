#!/usr/bin/env python3
"""Visible tests: battle mechanics verification."""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from emulator.game_engine import load_savestate, replay_actions, state_to_dict
from emulator.types import GameScreen

SAVESTATE = BASE / "savestates" / "battle_visible.json"
REFERENCE = BASE / "reference" / "battle_visible_result.json"


def load_reference():
    with open(REFERENCE) as f:
        return json.load(f)


def test_engine_loads_savestate():
    """Savestate loads without error and has expected structure."""
    state = load_savestate(str(SAVESTATE))
    assert state.screen == GameScreen.BATTLE_MAIN
    assert len(state.player_party) == 1
    assert state.player_party[0].species == "Blaziken"
    assert state.enemy_trainer is not None
    assert state.enemy_trainer.name == "Brawly"
    assert len(state.enemy_trainer.party) == 2
    assert state.battle_active is True


def test_engine_processes_actions():
    """Action sequence runs without crash and changes state."""
    ref = load_reference()
    state = load_savestate(str(SAVESTATE))
    initial_hp = state.enemy_trainer.party[0].hp

    state = replay_actions(state, ref["actions"])

    # State should have changed from initial
    assert state.action_count == ref["action_count"]


def test_battle_won():
    """Battle ends in player victory with all enemies defeated."""
    ref = load_reference()
    state = load_savestate(str(SAVESTATE))
    state = replay_actions(state, ref["actions"])

    result = state_to_dict(state)
    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won"
    assert result["whiteout"] is False, "Player should not have whited out"


def test_action_count_under_cap():
    """Solution uses a reasonable number of actions (<=60)."""
    ref = load_reference()
    assert ref["action_count"] <= 60, (
        f"Action count {ref['action_count']} exceeds cap of 60"
    )


def test_no_softlock():
    """Game state is not stuck in a menu loop after battle."""
    ref = load_reference()
    state = load_savestate(str(SAVESTATE))
    state = replay_actions(state, ref["actions"])

    # After battle, should not be in battle screens
    assert state.screen in (
        GameScreen.OVERWORLD, GameScreen.DIALOGUE
    ), f"Post-battle screen should be overworld or dialogue, got {state.screen}"
    assert state.battle_active is False, "Battle should not be active after winning"


def test_deterministic_replay():
    """Replaying same actions produces identical state."""
    ref = load_reference()

    state1 = load_savestate(str(SAVESTATE))
    state1 = replay_actions(state1, ref["actions"])
    result1 = state_to_dict(state1)

    state2 = load_savestate(str(SAVESTATE))
    state2 = replay_actions(state2, ref["actions"])
    result2 = state_to_dict(state2)

    assert result1 == result2, "Two replays of same actions should produce identical state"


def test_dual_type_effectiveness():
    """Type effectiveness must be multiplicative for dual-type defenders.

    Grass vs Aron (Steel/Rock): Grass->Steel = 0.5x, Grass->Rock = 2.0x
    Correct (multiplicative): 0.5 * 2.0 = 1.0x
    Buggy (additive):  1.0 + (0.5-1) + (2.0-1) = 1.5x
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    shroomish = PokemonInstance(
        species="Shroomish", level=20, hp=50, max_hp=50,
        attack=40, defense=40, sp_atk=40, sp_def=40, speed=35,
        moves=["Razor Leaf"], pp=[25],
    )
    aron = PokemonInstance(
        species="Aron", level=20, hp=50, max_hp=50,
        attack=50, defense=70, sp_atk=40, sp_def=40, speed=30,
        moves=["Rock Tomb"], pp=[10],
    )

    # Grass vs Aron (Steel/Rock): multiplicative = 0.5 * 2.0 = 1.0x (neutral)
    damage = calculate_damage(shroomish, aron, "Razor Leaf")

    # Create a Normal-type defender with same stats to get baseline neutral damage
    normal_defender = PokemonInstance(
        species="Poochyena", level=20, hp=50, max_hp=50,
        attack=50, defense=70, sp_atk=40, sp_def=40, speed=30,
        moves=["Tackle"], pp=[35],
    )
    # Grass vs Dark = 1.0x (neutral)
    neutral_damage = calculate_damage(shroomish, normal_defender, "Razor Leaf")

    # With correct multiplicative effectiveness (1.0x), damage against Aron
    # should equal neutral damage (both are 1.0x effective with same def stat)
    assert damage == neutral_damage, (
        f"Dual-type effectiveness should be multiplicative: Grass vs Steel/Rock "
        f"= 0.5*2.0 = 1.0x (neutral). Got damage={damage} vs neutral={neutral_damage}. "
        f"If damage > neutral, the bug is additive combination."
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
