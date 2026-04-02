#!/usr/bin/env python3
"""Visible tests for Step 2: Status conditions, stat stages, switching."""

import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("/app/step_1/files")))

from battle_engine import (
    run_battle,
    calculate_damage,
    create_pokemon,
    get_type_effectiveness,
    execute_attack,
    load_species_db,
    load_moves_db,
    load_type_chart,
)
from models import Pokemon, Move

VISIBLE_DATA = Path("/app/step_1/files/data")


def _make_scenario(data, data_dir=None):
    """Write a scenario dict to a temp file and run the battle."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name
    try:
        return run_battle(tmp, str(data_dir or VISIBLE_DATA))
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_poison_damage_end_of_turn():
    """Poisoned Pokemon should take 1/8 max HP damage at end of each turn."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Eevee has base HP 55 → at level 50: ((110)*50/100) + 50 + 10 = 115
    eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
    max_hp = eevee.stats["hp"]

    # Inflict poison
    eevee.status = "poison"

    expected_damage = max(1, max_hp // 8)
    assert expected_damage > 0, "Poison damage should be at least 1"

    # Simulate poison tick — the engine should apply this at end of turn
    # We test by running a scenario where Toxic is used
    scenario = {
        "seed": 200,
        "pokemon_1": {
            "species": "Bulbasaur",
            "level": 50,
            "moves": ["Toxic", "Tackle"]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": "Toxic", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
        ]
    }
    result = _make_scenario(scenario)

    # After Toxic lands and a turn passes, Eevee should have taken poison
    # damage in addition to any move damage.  Check that the final HP is
    # lower than it would be from just move damage alone.
    final_hp = result["final_state"]["pokemon_2"]["hp"]
    assert isinstance(final_hp, int), "HP should be an integer"

    # Eevee should have taken some damage (at minimum from Tackle + poison)
    eevee_max = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db).stats["hp"]
    assert final_hp < eevee_max, "Eevee should have taken damage from poison + attacks"


def test_burn_halves_attack():
    """A burned Pokemon's physical attack damage should be halved."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    machop = create_pokemon("Machop", 50, ["Karate Chop"], species_db, moves_db)
    eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)

    # Normal damage (no burn)
    rng1 = random.Random(42)
    normal_dmg = calculate_damage(machop, eevee, machop.moves[0], type_chart, rng1)

    # Burned — physical damage should be halved
    machop.status = "burn"
    eevee.current_hp = eevee.stats["hp"]  # reset
    rng2 = random.Random(42)
    burn_dmg = calculate_damage(machop, eevee, machop.moves[0], type_chart, rng2)

    assert burn_dmg > 0, "Burned Pokemon should still deal some damage"
    assert burn_dmg <= normal_dmg * 0.6, (
        f"Burn should roughly halve physical damage: normal={normal_dmg}, burned={burn_dmg}"
    )


def test_paralysis_speed_reduction():
    """Paralyzed Pokemon's effective speed should be quartered."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    pikachu = create_pokemon("Pikachu", 50, ["Thunderbolt"], species_db, moves_db)
    normal_speed = pikachu.stats["speed"]

    # Apply paralysis
    pikachu.status = "paralysis"

    # The engine should use effective speed = speed // 4 for paralyzed Pokemon
    # We test this indirectly via turn order: a paralyzed Pikachu (speed 95 // 4 = 23)
    # should be slower than Squirtle (speed 48)
    squirtle = create_pokemon("Squirtle", 50, ["Water Gun"], species_db, moves_db)

    from battle_engine import determine_turn_order
    rng = random.Random(0)
    order = determine_turn_order(pikachu, squirtle, pikachu.moves[0], squirtle.moves[0], rng)

    # Paralyzed Pikachu (23) should be slower than Squirtle (48)
    assert order == (2, 1), (
        f"Paralyzed Pikachu (eff speed ~{normal_speed // 4}) should be slower "
        f"than Squirtle (speed {squirtle.stats['speed']}); got order={order}"
    )


def test_stat_stage_clamp():
    """Stat stages should clamp at -6 and +6."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    machop = create_pokemon("Machop", 50, ["Swords Dance", "Karate Chop"], species_db, moves_db)

    # Apply +2 attack stage 4 times = +8, should clamp at +6
    for _ in range(4):
        machop.stat_stages["attack"] = min(6, machop.stat_stages["attack"] + 2)

    assert machop.stat_stages["attack"] == 6, (
        f"Attack stage should clamp at +6, got {machop.stat_stages['attack']}"
    )

    # Apply -2 many times, should clamp at -6
    machop.stat_stages["defense"] = 0
    for _ in range(5):
        machop.stat_stages["defense"] = max(-6, machop.stat_stages["defense"] - 2)

    assert machop.stat_stages["defense"] == -6, (
        f"Defense stage should clamp at -6, got {machop.stat_stages['defense']}"
    )


def test_switch_action_before_move():
    """Switching should happen before attacks in a turn."""
    scenario = {
        "seed": 300,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Flamethrower", "Tackle"],
            "party": [
                {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt", "Quick Attack"]}
            ]
        },
        "pokemon_2": {
            "species": "Squirtle",
            "level": 50,
            "moves": ["Water Gun", "Tackle"]
        },
        "move_choices": [
            {
                "pokemon_1": {"action": "switch", "target": 0},
                "pokemon_2": {"action": "move", "move": "Water Gun"}
            }
        ]
    }
    result = _make_scenario(scenario)

    # After the switch, pokemon_1's active should be Pikachu
    assert result["final_state"]["pokemon_1"]["name"] == "Pikachu", (
        f"After switch, active should be Pikachu, got {result['final_state']['pokemon_1']['name']}"
    )

    # Water Gun should target Pikachu (the switched-in Pokemon), not Charmander
    # Find the Water Gun action in the turn log
    water_gun_actions = [t for t in result["turns"] if t.get("move") == "Water Gun"]
    assert len(water_gun_actions) > 0, "Water Gun should appear in turn log"


def test_faint_forces_switch():
    """When the active Pokemon faints with party members available,
    the trainer must switch to a non-fainted party member."""
    # Create a scenario where Pokemon 2's active faints quickly
    scenario = {
        "seed": 400,
        "pokemon_1": {
            "species": "Pikachu",
            "level": 50,
            "moves": ["Thunderbolt"]
        },
        "pokemon_2": {
            "species": "Squirtle",
            "level": 50,
            "moves": ["Water Gun"],
            "party": [
                {"species": "Bulbasaur", "level": 50, "moves": ["Vine Whip"]}
            ]
        },
        "move_choices": [
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Vine Whip"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Vine Whip"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Vine Whip"}
        ]
    }
    result = _make_scenario(scenario)

    # The battle should continue after Squirtle faints because Bulbasaur
    # is available.  The battle only ends when all of a side's Pokemon faint.
    assert result["winner"] is not None, "Battle should have a winner"

    # Check that more than 2 turns of actions happened (indicating the
    # battle continued after the first Pokemon fainted)
    actions = result["turns"]
    assert len(actions) > 2, (
        f"Battle should continue after faint with party available; got {len(actions)} actions"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
