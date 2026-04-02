#!/usr/bin/env python3
"""Visible tests for Step 1: Core 1v1 battle engine."""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/app/step_1/files")))

from battle_engine import (
    run_battle,
    calculate_damage,
    create_pokemon,
    get_type_effectiveness,
    determine_turn_order,
    calculate_stat,
    load_species_db,
    load_moves_db,
    load_type_chart,
)
from models import Pokemon, Move, TurnResult

DATA_DIR = Path("/app/step_1/files/data")
SCENARIO_01 = str(DATA_DIR / "scenario_public_01.json")


def test_engine_loads_scenario():
    """Scenario JSON loads and engine runs without error."""
    result = run_battle(SCENARIO_01, str(DATA_DIR))
    assert isinstance(result, dict), "run_battle must return a dict"
    assert "winner" in result, "Result must contain 'winner'"
    assert "turns" in result, "Result must contain 'turns'"
    assert "final_state" in result, "Result must contain 'final_state'"
    assert isinstance(result["turns"], list), "turns must be a list"
    assert len(result["turns"]) > 0, "Battle must have at least one turn action"


def test_public_battle_winner():
    """Pikachu (Electric) should beat Squirtle (Water) with type advantage.

    Thunderbolt is Electric-type with STAB (1.5x) and is super effective
    against Water (2.0x).  Pikachu is faster (speed 90 vs 43), so it
    attacks first every turn.  Pikachu should win decisively.
    """
    result = run_battle(SCENARIO_01, str(DATA_DIR))
    assert result["winner"] == "Pikachu", (
        f"Expected Pikachu to win, got winner={result['winner']}"
    )
    final = result["final_state"]
    assert final["pokemon_1"]["hp"] > 0, "Pikachu should have HP remaining"
    assert final["pokemon_2"]["hp"] == 0, "Squirtle should be fainted"


def test_turn_order_speed_based():
    """The faster Pokemon (by Speed stat) should attack first each turn."""
    species_db = load_species_db(str(DATA_DIR))
    moves_db = load_moves_db(str(DATA_DIR))

    # Pikachu base speed 90, Squirtle base speed 43
    pikachu = create_pokemon("Pikachu", 50, ["Thunderbolt"], species_db, moves_db)
    squirtle = create_pokemon("Squirtle", 50, ["Water Gun"], species_db, moves_db)

    assert pikachu.stats["speed"] > squirtle.stats["speed"], (
        "Pikachu should have higher speed stat"
    )

    rng = random.Random(0)
    move_p = pikachu.moves[0]
    move_s = squirtle.moves[0]

    order = determine_turn_order(pikachu, squirtle, move_p, move_s, rng)
    assert order == (1, 2), (
        f"Pikachu (faster) should go first; got order={order}"
    )


def test_type_effectiveness_applied():
    """Electric vs Water should be super effective (2.0x multiplier)."""
    type_chart = load_type_chart(str(DATA_DIR))

    # Electric attacking Water type
    eff = get_type_effectiveness("Electric", ["Water"], type_chart)
    assert eff == 2.0, f"Electric vs Water should be 2.0x, got {eff}"

    # Fire attacking Grass type
    eff2 = get_type_effectiveness("Fire", ["Grass"], type_chart)
    assert eff2 == 2.0, f"Fire vs Grass should be 2.0x, got {eff2}"

    # Normal attacking Ghost type — immune
    eff3 = get_type_effectiveness("Normal", ["Ghost"], type_chart)
    assert eff3 == 0.0, f"Normal vs Ghost should be 0.0x, got {eff3}"


def test_deterministic_same_seed():
    """Running the same scenario twice must produce identical output."""
    result_1 = run_battle(SCENARIO_01, str(DATA_DIR))
    result_2 = run_battle(SCENARIO_01, str(DATA_DIR))

    assert result_1["winner"] == result_2["winner"], "Winner must be identical"
    assert result_1["turns"] == result_2["turns"], "Turn log must be identical"
    assert result_1["final_state"] == result_2["final_state"], (
        "Final state must be identical"
    )


def test_damage_formula_range():
    """Thunderbolt damage vs Squirtle should be in an expected range.

    With STAB (1.5x) and super effective (2.0x), the modifier is 3.0x.
    At level 50, base damage is roughly 33, so final damage should be
    in the range of ~85-100 for each hit (with 85-100% random factor).
    """
    species_db = load_species_db(str(DATA_DIR))
    moves_db = load_moves_db(str(DATA_DIR))
    type_chart = load_type_chart(str(DATA_DIR))

    pikachu = create_pokemon("Pikachu", 50, ["Thunderbolt"], species_db, moves_db)
    squirtle = create_pokemon("Squirtle", 50, ["Water Gun"], species_db, moves_db)

    damages = []
    for seed in range(50):
        rng = random.Random(seed)
        squirtle.current_hp = squirtle.stats["hp"]  # reset
        dmg = calculate_damage(pikachu, squirtle, pikachu.moves[0], type_chart, rng)
        damages.append(dmg)

    # All damages should be positive (Electric is super effective vs Water)
    assert all(d > 0 for d in damages), (
        f"All damages should be > 0 for super-effective hit; got {damages}"
    )

    # With correct formula: modifier = 1.5 * 2.0 = 3.0
    # base ≈ 33.5, so damage ≈ 85-100
    # Allow generous bounds to catch miscalculated modifiers
    avg_damage = sum(damages) / len(damages)
    assert 80 <= avg_damage <= 110, (
        f"Average damage {avg_damage:.1f} outside expected range 80-110"
    )

    # Min damage should not be absurdly low (would indicate wrong multiplier)
    assert min(damages) >= 75, (
        f"Min damage {min(damages)} too low for STAB + super effective"
    )

    # Max damage should not be absurdly high
    assert max(damages) <= 120, (
        f"Max damage {max(damages)} too high — check damage formula"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
