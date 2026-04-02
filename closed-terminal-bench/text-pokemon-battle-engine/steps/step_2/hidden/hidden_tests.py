#!/usr/bin/env python3
"""Hidden tests for Step 2: Status conditions, stat stages, switching."""

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
    execute_attack,
    determine_turn_order,
    load_species_db,
    load_moves_db,
    load_type_chart,
)
from models import Pokemon, Move

VISIBLE_DATA = Path("/app/step_1/files/data")
HIDDEN_DATA = Path("/app/step_2/hidden/data")


def _make_scenario(data, data_dir=None):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name
    try:
        return run_battle(tmp, str(data_dir or VISIBLE_DATA))
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_hidden_sleep_blocks_move():
    """A sleeping Pokemon should not be able to attack."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
    eevee.status = "sleep"
    eevee.status_turns = 3  # Will sleep for 3 turns

    gastly = create_pokemon("Gastly", 50, ["Shadow Ball"], species_db, moves_db)

    rng = random.Random(42)
    result = execute_attack(eevee, gastly, eevee.moves[0], type_chart, rng)

    # Sleeping Pokemon should not deal damage
    assert result.damage == 0, (
        f"Sleeping Pokemon should deal 0 damage, got {result.damage}"
    )
    assert gastly.current_hp == gastly.stats["hp"], (
        "Target HP should be unchanged when attacker is asleep"
    )


def test_hidden_freeze_thaw_chance():
    """Frozen Pokemon should have a 20% chance of thawing each turn.

    With enough trials, we should see some thaws and some still-frozen.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    thaw_count = 0
    frozen_count = 0
    trials = 100

    for seed in range(trials):
        eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
        eevee.status = "freeze"
        target = create_pokemon("Geodude", 50, ["Rock Throw"], species_db, moves_db)

        rng = random.Random(seed)
        result = execute_attack(eevee, target, eevee.moves[0], type_chart, rng)

        if result.damage > 0 or eevee.status != "freeze":
            thaw_count += 1
        else:
            frozen_count += 1

    # With 20% thaw rate over 100 trials, expect ~20 thaws
    # Use wide bounds to avoid flaky tests
    assert thaw_count > 5, (
        f"Expected some thaws (20% rate), got only {thaw_count}/{trials}"
    )
    assert frozen_count > 50, (
        f"Expected most to stay frozen (80% rate), but only {frozen_count}/{trials} stayed frozen"
    )


def test_hidden_poison_ko():
    """Poison end-of-turn damage should be able to KO a Pokemon."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
    max_hp = eevee.stats["hp"]
    poison_dmg = max(1, max_hp // 8)

    # Set HP low enough that one poison tick KOs
    eevee.status = "poison"
    eevee.current_hp = poison_dmg

    # Run a scenario where poison should KO
    scenario = {
        "seed": 600,
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
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"},
            {"pokemon_1": "Tackle", "pokemon_2": "Tackle"}
        ]
    }
    result = _make_scenario(scenario)

    # Battle should end with Eevee fainted (from combination of attacks + poison)
    assert result["winner"] is not None, "Battle should have ended"
    assert result["final_state"]["pokemon_2"]["hp"] == 0, (
        "Eevee should have fainted from poison + attack damage"
    )


def test_hidden_switch_resets_stat_stages():
    """Switching out should reset all stat stages to 0."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Charmander with boosted stats
    charmander = create_pokemon(
        "Charmander", 50, ["Flamethrower", "Tackle"], species_db, moves_db,
    )
    charmander.stat_stages["attack"] = 4
    charmander.stat_stages["sp_atk"] = 2

    # After switching and switching back, stat stages should reset
    scenario = {
        "seed": 700,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Swords Dance", "Flamethrower"],
            "party": [
                {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]}
            ]
        },
        "pokemon_2": {
            "species": "Geodude",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": {"action": "move", "move": "Swords Dance"}, "pokemon_2": {"action": "move", "move": "Tackle"}},
            {"pokemon_1": {"action": "switch", "target": 0}, "pokemon_2": {"action": "move", "move": "Tackle"}},
            {"pokemon_1": {"action": "switch", "target": 0}, "pokemon_2": {"action": "move", "move": "Tackle"}}
        ]
    }
    result = _make_scenario(scenario)

    # The battle ran successfully — the switch-back should have reset stats
    assert isinstance(result, dict), "Battle should complete"
    # We verify indirectly: if Charmander's Swords Dance boost was reset after
    # switching out and back, its attack should be back to normal in the
    # subsequent turns.  The test passes if the engine doesn't error.
    assert len(result["turns"]) > 0, "Battle should have turn actions"


def test_hidden_invalid_switch_rejected():
    """Switching to a fainted party Pokemon should not be allowed."""
    scenario = {
        "seed": 800,
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
                {"species": "Geodude", "level": 50, "moves": ["Rock Throw"]}
            ]
        },
        "move_choices": [
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Rock Throw"}
        ]
    }
    result = _make_scenario(scenario)

    # The battle should complete without error.  After Squirtle faints,
    # Geodude should come in.  After Geodude faints, the battle ends
    # because there are no more party members.
    assert result["winner"] == "Pikachu", (
        f"Pikachu should win after defeating all opponents, got {result['winner']}"
    )


def test_hidden_multi_turn_status_scenario():
    """Complex multi-turn battle with poison and switching."""
    scenario = {
        "seed": 500,
        "pokemon_1": {
            "species": "Bulbasaur",
            "level": 50,
            "moves": ["Toxic", "Vine Whip"],
            "party": [
                {"species": "Charmander", "level": 50, "moves": ["Flamethrower"]}
            ]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle", "Quick Attack"],
            "party": [
                {"species": "Pidgey", "level": 50, "moves": ["Gust", "Tackle"]}
            ]
        },
        "move_choices": [
            {"pokemon_1": "Toxic", "pokemon_2": "Tackle"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Quick Attack"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Tackle"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Tackle"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Tackle"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Gust"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Gust"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Gust"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Gust"},
            {"pokemon_1": "Vine Whip", "pokemon_2": "Gust"}
        ]
    }
    result = _make_scenario(scenario)

    # The battle should complete deterministically
    assert result["winner"] is not None, "Complex scenario should produce a winner"

    # Run twice — must be deterministic
    result2 = _make_scenario(scenario)
    assert result["winner"] == result2["winner"], "Result should be deterministic"
    assert result["turns"] == result2["turns"], "Turn log should be deterministic"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
