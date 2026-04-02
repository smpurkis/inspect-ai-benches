#!/usr/bin/env python3
"""Hidden tests for the core 1v1 battle engine."""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/app/files")))

from battle_engine import (
    run_battle,
    calculate_damage,
    create_pokemon,
    get_type_effectiveness,
    determine_turn_order,
    load_species_db,
    load_moves_db,
    load_type_chart,
)
from models import Pokemon, Move

VISIBLE_DATA = Path("/app/files/data")
HIDDEN_DATA = Path("/app/hidden/data")
SCENARIO_HIDDEN = str(HIDDEN_DATA / "scenario_hidden_02.json")


def test_hidden_scenario_02_winner():
    """Charmander (Fire) should beat Bulbasaur (Grass/Poison).

    Flamethrower has STAB (1.5x) and is super effective vs Grass (2.0x)
    for a 3.0x modifier.  Charmander is faster (speed 65 vs 45).
    """
    result = run_battle(SCENARIO_HIDDEN, str(VISIBLE_DATA))
    assert result["winner"] == "Charmander", (
        f"Expected Charmander to win, got {result['winner']}"
    )
    final = result["final_state"]
    assert final["pokemon_1"]["hp"] > 0, "Charmander should have HP remaining"
    assert final["pokemon_2"]["hp"] == 0, "Bulbasaur should be fainted"


def test_hidden_not_very_effective():
    """Grass attacking Fire should be not very effective (0.5x)."""
    type_chart = load_type_chart(str(VISIBLE_DATA))
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Grass vs Fire = 0.5x
    eff = get_type_effectiveness("Grass", ["Fire"], type_chart)
    assert eff == 0.5, f"Grass vs Fire should be 0.5x, got {eff}"

    # Verify damage is lower for not-very-effective vs neutral
    bulbasaur = create_pokemon("Bulbasaur", 50, ["Vine Whip", "Tackle"], species_db, moves_db)
    charmander = create_pokemon("Charmander", 50, ["Flamethrower"], species_db, moves_db)

    rng1 = random.Random(777)
    rng2 = random.Random(777)

    # Vine Whip (Grass) vs Charmander (Fire) — STAB 1.5x, NVE 0.5x = 0.75x total
    dmg_nve = calculate_damage(bulbasaur, charmander, bulbasaur.moves[0], type_chart, rng1)
    # Tackle (Normal) vs Charmander (Fire) — no STAB, neutral 1.0x
    charmander.current_hp = charmander.stats["hp"]  # reset
    dmg_neutral = calculate_damage(bulbasaur, charmander, bulbasaur.moves[1], type_chart, rng2)

    # Vine Whip has slightly higher power (45 vs 40) but NVE should keep
    # STAB-boosted Grass damage from being dramatically higher
    # The key check is that the effectiveness was applied correctly
    assert dmg_nve > 0, "Not-very-effective should still deal some damage"
    assert dmg_neutral > 0, "Neutral hit should deal damage"


def test_hidden_immune_type():
    """Normal moves should deal 0 damage to Ghost types."""
    type_chart = load_type_chart(str(VISIBLE_DATA))
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    eff = get_type_effectiveness("Normal", ["Ghost", "Poison"], type_chart)
    assert eff == 0.0, f"Normal vs Ghost/Poison should be 0.0x, got {eff}"

    # Eevee (Normal) using Tackle vs Gastly (Ghost/Poison)
    eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
    gastly = create_pokemon("Gastly", 50, ["Shadow Ball"], species_db, moves_db)

    rng = random.Random(12345)
    dmg = calculate_damage(eevee, gastly, eevee.moves[0], type_chart, rng)
    assert dmg == 0, f"Normal vs Ghost should deal 0 damage, got {dmg}"
    assert gastly.current_hp == gastly.stats["hp"], "Gastly HP should be unchanged"


def test_hidden_faint_ends_battle():
    """When a Pokemon faints from the first attack, the fainted Pokemon
    should NOT get to attack in the same turn.

    Create a scenario where the first attacker is guaranteed to KO the
    defender in one hit.  The turn log should only contain one attack for
    that turn, not two.
    """
    type_chart = load_type_chart(str(VISIBLE_DATA))
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Abra (Psychic, speed 90) with Psychic vs Machop (Fighting, speed 35)
    # Psychic is super effective (2x) vs Fighting, with STAB (1.5x) = 3.0x
    # Abra SpAtk is very high (base 105), Machop SpDef is low (base 35)
    # This should be a guaranteed OHKO
    scenario = {
        "seed": 99,
        "pokemon_1": {
            "species": "Abra",
            "level": 50,
            "moves": ["Psychic"]
        },
        "pokemon_2": {
            "species": "Machop",
            "level": 50,
            "moves": ["Karate Chop"]
        },
        "move_choices": [
            {"pokemon_1": "Psychic", "pokemon_2": "Karate Chop"}
        ]
    }

    # Write temporary scenario
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(scenario, f)
        tmp_path = f.name

    try:
        result = run_battle(tmp_path, str(VISIBLE_DATA))

        # Abra should win by OHKO
        assert result["winner"] == "Abra", (
            f"Abra should OHKO Machop, got winner={result['winner']}"
        )

        # The turn log should show only 1 attack action for turn 1
        # (Abra attacks, Machop faints, Machop does NOT get to counter-attack)
        actions = result["turns"]
        assert len(actions) == 1, (
            f"Expected 1 action (OHKO), got {len(actions)} actions: "
            f"{[a.get('attacker', '?') + ':' + a.get('move', '?') for a in actions]}"
        )
        assert actions[0]["attacker"] == "Abra", "Abra should be the sole attacker"
        assert actions[0]["defender_hp_after"] == 0, "Machop should have 0 HP"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_hidden_pp_depletion():
    """A move with 0 PP remaining should not be usable; the engine should
    fall back to the next available move or Struggle.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    pikachu = create_pokemon("Pikachu", 50, ["Thunderbolt", "Quick Attack"], species_db, moves_db)
    squirtle = create_pokemon("Squirtle", 50, ["Water Gun", "Tackle"], species_db, moves_db)

    # Deplete Thunderbolt PP
    pikachu.moves[0].current_pp = 0

    # In auto-select mode, should pick Quick Attack (the next move with PP)
    scenario = {
        "seed": 55,
        "pokemon_1": {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt", "Quick Attack"]},
        "pokemon_2": {"species": "Squirtle", "level": 50, "moves": ["Water Gun", "Tackle"]},
        "max_turns": 1,
    }

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(scenario, f)
        tmp_path = f.name

    try:
        # Run a full battle — the auto-select should choose the first move with PP
        result = run_battle(tmp_path, str(VISIBLE_DATA))
        # Verify the battle ran without error
        assert isinstance(result, dict)
        assert len(result["turns"]) > 0

        # Now test directly: calling execute_attack with 0 PP should give Struggle
        from battle_engine import execute_attack
        pkchu = create_pokemon("Pikachu", 50, ["Thunderbolt"], species_db, moves_db)
        sqrtl = create_pokemon("Squirtle", 50, ["Water Gun"], species_db, moves_db)
        pkchu.moves[0].current_pp = 0

        rng = random.Random(0)
        res = execute_attack(pkchu, sqrtl, pkchu.moves[0], type_chart, rng)
        assert res.move == "Struggle", (
            f"Expected Struggle when PP=0, got {res.move}"
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_hidden_same_speed_tiebreak():
    """Two Pokemon with identical speed stats should have a deterministic
    tiebreak based on the RNG seed.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Eevee (speed 55) vs itself — same species, same speed
    eevee_1 = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
    eevee_2 = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)
    eevee_1.name = "Eevee_A"
    eevee_2.name = "Eevee_B"

    assert eevee_1.stats["speed"] == eevee_2.stats["speed"], (
        "Both Eevees should have identical speed"
    )

    # Run the tiebreak 10 times with the same seed — should get same result
    results = []
    for _ in range(10):
        rng = random.Random(42)
        order = determine_turn_order(
            eevee_1, eevee_2, eevee_1.moves[0], eevee_2.moves[0], rng,
        )
        results.append(order)

    assert all(r == results[0] for r in results), (
        f"Tiebreak should be deterministic with same seed; got {results}"
    )

    # Different seeds should potentially give different results
    orders_varied = set()
    for seed in range(100):
        rng = random.Random(seed)
        order = determine_turn_order(
            eevee_1, eevee_2, eevee_1.moves[0], eevee_2.moves[0], rng,
        )
        orders_varied.add(order)

    assert len(orders_varied) == 2, (
        f"Over 100 seeds, should see both orderings for tied speeds; got {orders_varied}"
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
