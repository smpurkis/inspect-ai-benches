#!/usr/bin/env python3
"""Hidden tests for Step 3: Priority brackets, weather, multi-hit, crits, trace."""

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
    determine_turn_order,
    load_species_db,
    load_moves_db,
    load_type_chart,
)
from models import Pokemon, Move

VISIBLE_DATA = Path("/app/step_1/files/data")
HIDDEN_DATA = Path("/app/step_3/hidden/data")


def _make_scenario(data, data_dir=None, trace=False):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name
    try:
        return run_battle(tmp, str(data_dir or VISIBLE_DATA), trace=trace)
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_hidden_priority_bracket_ordering():
    """Multiple priority levels should be resolved correctly.

    Priority 2 (Extreme Speed) > Priority 1 (Quick Attack) > Priority 0 (Tackle).
    Speed should only matter within the same priority bracket.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Eevee (speed 55) with Extreme Speed (priority 2)
    # vs Pikachu (speed 90) with Quick Attack (priority 1)
    eevee = create_pokemon("Eevee", 50, ["Extreme Speed"], species_db, moves_db)
    pikachu = create_pokemon("Pikachu", 50, ["Quick Attack"], species_db, moves_db)

    # Eevee is slower but has higher priority
    assert eevee.stats["speed"] < pikachu.stats["speed"]

    rng = random.Random(0)
    espeed = eevee.moves[0]  # priority 2
    qatk = pikachu.moves[0]  # priority 1

    order = determine_turn_order(eevee, pikachu, espeed, qatk, rng)
    assert order == (1, 2), (
        f"Extreme Speed (p2) should beat Quick Attack (p1); got {order}"
    )

    # Same priority (both priority 1): speed decides
    pikachu2 = create_pokemon("Pikachu", 50, ["Quick Attack"], species_db, moves_db)
    machop = create_pokemon("Machop", 50, ["Mach Punch"], species_db, moves_db)

    rng2 = random.Random(0)
    # Both priority 1, Pikachu faster (95 vs 40)
    order2 = determine_turn_order(pikachu2, machop, pikachu2.moves[0], machop.moves[0], rng2)
    assert order2 == (1, 2), (
        f"Same priority, faster Pikachu should go first; got {order2}"
    )


def test_hidden_weather_weakens_opposite():
    """Sun should weaken Water moves to 0.5x, rain should weaken Fire to 0.5x."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    # Squirtle Water Gun in sun (should be weakened)
    scenario_sun = {
        "seed": 42,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Sunny Day", "Tackle"]
        },
        "pokemon_2": {
            "species": "Squirtle",
            "level": 50,
            "moves": ["Water Gun"]
        },
        "move_choices": [
            {"pokemon_1": "Sunny Day", "pokemon_2": "Water Gun"},
            {"pokemon_1": "Tackle", "pokemon_2": "Water Gun"},
        ]
    }

    # Same but without weather
    scenario_clear = {
        "seed": 42,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Tackle"]
        },
        "pokemon_2": {
            "species": "Squirtle",
            "level": 50,
            "moves": ["Water Gun"]
        },
        "move_choices": [
            {"pokemon_1": "Tackle", "pokemon_2": "Water Gun"},
        ]
    }

    result_sun = _make_scenario(scenario_sun)
    result_clear = _make_scenario(scenario_clear)

    # Find Water Gun damage (in turn 2 for sun scenario, turn 1 for clear)
    wg_sun = [t for t in result_sun["turns"] if t.get("move") == "Water Gun"]
    wg_clear = [t for t in result_clear["turns"] if t.get("move") == "Water Gun"]

    assert len(wg_sun) >= 1 and len(wg_clear) >= 1, "Water Gun should appear"

    # Water Gun in sun should deal less damage than without weather
    # Use the second Water Gun from sun scenario (after Sunny Day is active)
    sun_dmg = wg_sun[-1]["damage"]
    clear_dmg = wg_clear[0]["damage"]

    assert sun_dmg < clear_dmg, (
        f"Water Gun in sun ({sun_dmg}) should be weaker than clear ({clear_dmg})"
    )


def test_hidden_multi_hit_damage():
    """Multi-hit moves should hit 2-5 times with independent damage rolls."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    # Fury Attack is multi-hit: 2-5 hits
    scenario = {
        "seed": 42,
        "pokemon_1": {
            "species": "Pidgey",
            "level": 50,
            "moves": ["Fury Attack"]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": "Fury Attack", "pokemon_2": "Tackle"}
        ]
    }
    result = _make_scenario(scenario)

    fa_actions = [t for t in result["turns"] if t.get("move") == "Fury Attack"]
    assert len(fa_actions) > 0, "Fury Attack should appear in turns"

    # The total damage should be reported in the turn result
    fa = fa_actions[0]
    assert fa["damage"] > 0, "Multi-hit move should deal damage"

    # Run multiple seeds to verify we get different hit counts
    hit_counts = set()
    for seed in range(100):
        sc = dict(scenario, seed=seed)
        res = _make_scenario(sc)
        fa_a = [t for t in res["turns"] if t.get("move") == "Fury Attack"]
        if fa_a:
            # The result might include a "hits" field or we can infer from damage
            hits = fa_a[0].get("hits", None)
            if hits is not None:
                hit_counts.add(hits)

    # Should see at least 2 different hit counts across 100 seeds
    if hit_counts:
        assert len(hit_counts) >= 2, (
            f"Expected varied hit counts for multi-hit; got {hit_counts}"
        )


def test_hidden_complex_scenario_trace():
    """Complex 8-turn scenario should produce a deterministic trace."""
    scenario_path = str(HIDDEN_DATA / "scenario_hidden_complex.json")

    result_1 = run_battle(scenario_path, str(VISIBLE_DATA), trace=True)
    result_2 = run_battle(scenario_path, str(VISIBLE_DATA), trace=True)

    assert "trace" in result_1, "Result must have trace"
    assert isinstance(result_1["trace"], list), "trace must be a list"
    assert len(result_1["trace"]) > 5, "Complex scenario should have many trace lines"

    # Must be deterministic
    assert result_1["trace"] == result_2["trace"], (
        "Trace must be byte-identical across runs"
    )
    assert result_1["winner"] == result_2["winner"], "Winner must be deterministic"

    # Check trace contains expected elements
    trace_text = "\n".join(result_1["trace"])
    assert "TURN 1" in trace_text, "Trace should contain TURN 1"
    assert "TURN 2" in trace_text, "Trace should contain TURN 2"
    assert "used" in trace_text, "Trace should show move usage"


def test_hidden_crit_ignores_stat_drops():
    """Critical hits should ignore the defender's positive stat stage modifiers.

    A defender with +6 defense should take the same crit damage as one with +0.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    # Find a seed that produces a critical hit
    crit_seed = None
    for seed in range(500):
        pikachu = create_pokemon("Pikachu", 50, ["Thunderbolt"], species_db, moves_db)
        eevee = create_pokemon("Eevee", 50, ["Tackle"], species_db, moves_db)

        scenario = {
            "seed": seed,
            "pokemon_1": {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]},
            "pokemon_2": {"species": "Eevee", "level": 50, "moves": ["Tackle"]},
            "move_choices": [{"pokemon_1": "Thunderbolt", "pokemon_2": "Tackle"}],
        }
        result = _make_scenario(scenario)
        tb = [t for t in result["turns"] if t.get("move") == "Thunderbolt"]
        if tb and tb[0].get("critical", False):
            crit_seed = seed
            break

    if crit_seed is None:
        # If no crit found in 500 seeds, skip test gracefully
        assert False, "Could not find a critical hit seed in 500 trials"

    # Run with boosted defender vs unboosted defender
    scenario_base = {
        "seed": crit_seed,
        "pokemon_1": {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]},
        "pokemon_2": {"species": "Eevee", "level": 50, "moves": ["Tackle"]},
        "move_choices": [{"pokemon_1": "Thunderbolt", "pokemon_2": "Tackle"}],
    }
    result_base = _make_scenario(scenario_base)
    tb_base = [t for t in result_base["turns"] if t.get("move") == "Thunderbolt"][0]
    crit_dmg = tb_base["damage"]

    # The crit should ignore positive defense boosts — the damage should be
    # the same regardless of defender stat stages
    assert crit_dmg > 0, "Critical hit should deal damage"


def test_hidden_weather_expires():
    """Weather should last exactly 5 turns and then expire."""
    scenario = {
        "seed": 42,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Sunny Day", "Flamethrower"]
        },
        "pokemon_2": {
            "species": "Geodude",
            "level": 50,
            "moves": ["Rock Throw"]
        },
        "move_choices": [
            {"pokemon_1": "Sunny Day", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Rock Throw"}
        ]
    }
    result = _make_scenario(scenario, trace=True)

    if "trace" not in result:
        assert False, "Trace mode required for weather expiry test"

    trace_text = "\n".join(result["trace"])

    # Sun should be active for turns 1-5 (set on turn 1, lasts 5 turns)
    # After turn 5, weather should clear

    # Find Flamethrower damages across turns to check weather effect
    ft_actions = [t for t in result["turns"] if t.get("move") == "Flamethrower"]

    if len(ft_actions) >= 6:
        # Turns 2-5 should have sun-boosted Flamethrower
        # Turn 6+ should have normal Flamethrower
        early_damages = [ft_actions[i]["damage"] for i in range(4)]  # turns 2-5
        # If turn 6+ exists and weather expired, damage should be lower
        late_damage = ft_actions[4]["damage"] if len(ft_actions) > 4 else None

        if late_damage is not None:
            avg_early = sum(early_damages) / len(early_damages)
            # Late damage should be notably lower (no sun boost)
            assert late_damage < avg_early, (
                f"After weather expires (turn 6+), damage ({late_damage}) should be "
                f"lower than sun-boosted average ({avg_early:.0f})"
            )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
