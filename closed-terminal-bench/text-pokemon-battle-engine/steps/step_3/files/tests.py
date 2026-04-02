#!/usr/bin/env python3
"""Visible tests for Step 3: Priority, weather, crits, and trace mode."""

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


def _make_scenario(data, data_dir=None, trace=False):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name
    try:
        return run_battle(tmp, str(data_dir or VISIBLE_DATA), trace=trace)
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_priority_move_goes_first():
    """A priority 1 move should go before a priority 0 move even if the
    user of the priority move is slower.

    Machop (speed 35) with Mach Punch (priority 1) vs Abra (speed 90)
    with Psychic (priority 0).  Machop should attack first.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))

    machop = create_pokemon("Machop", 50, ["Mach Punch"], species_db, moves_db)
    abra = create_pokemon("Abra", 50, ["Psychic"], species_db, moves_db)

    # Verify Machop is slower
    assert machop.stats["speed"] < abra.stats["speed"], "Machop should be slower"

    rng = random.Random(0)
    mach_punch = machop.moves[0]  # priority 1
    psychic = abra.moves[0]  # priority 0

    order = determine_turn_order(machop, abra, mach_punch, psychic, rng)
    assert order == (1, 2), (
        f"Mach Punch (priority 1) should go before Psychic (priority 0); got {order}"
    )


def test_weather_sun_boosts_fire():
    """Under sun weather, Fire-type moves should deal 1.5x damage."""
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    scenario_no_weather = {
        "seed": 42,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Flamethrower"]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": "Flamethrower", "pokemon_2": "Tackle"}
        ]
    }

    scenario_with_sun = {
        "seed": 42,
        "pokemon_1": {
            "species": "Charmander",
            "level": 50,
            "moves": ["Sunny Day", "Flamethrower"]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": "Sunny Day", "pokemon_2": "Tackle"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Tackle"}
        ]
    }

    result_no = _make_scenario(scenario_no_weather)
    result_sun = _make_scenario(scenario_with_sun)

    # Find Flamethrower damage in each
    flamethrower_no = [t for t in result_no["turns"] if t.get("move") == "Flamethrower"]
    flamethrower_sun = [t for t in result_sun["turns"] if t.get("move") == "Flamethrower"]

    assert len(flamethrower_no) > 0, "Flamethrower should appear in no-weather battle"
    assert len(flamethrower_sun) > 0, "Flamethrower should appear in sun battle"

    dmg_no = flamethrower_no[0]["damage"]
    dmg_sun = flamethrower_sun[0]["damage"]

    # Sun should boost fire damage by 1.5x (within some tolerance for RNG)
    assert dmg_sun > dmg_no, (
        f"Fire damage in sun ({dmg_sun}) should exceed normal ({dmg_no})"
    )


def test_weather_rain_boosts_water():
    """Under rain weather, Water-type moves should deal 1.5x damage."""
    scenario_no_rain = {
        "seed": 42,
        "pokemon_1": {
            "species": "Squirtle",
            "level": 50,
            "moves": ["Water Gun"]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": "Water Gun", "pokemon_2": "Tackle"}
        ]
    }

    scenario_with_rain = {
        "seed": 42,
        "pokemon_1": {
            "species": "Squirtle",
            "level": 50,
            "moves": ["Rain Dance", "Water Gun"]
        },
        "pokemon_2": {
            "species": "Eevee",
            "level": 50,
            "moves": ["Tackle"]
        },
        "move_choices": [
            {"pokemon_1": "Rain Dance", "pokemon_2": "Tackle"},
            {"pokemon_1": "Water Gun", "pokemon_2": "Tackle"}
        ]
    }

    result_no = _make_scenario(scenario_no_rain)
    result_rain = _make_scenario(scenario_with_rain)

    wg_no = [t for t in result_no["turns"] if t.get("move") == "Water Gun"]
    wg_rain = [t for t in result_rain["turns"] if t.get("move") == "Water Gun"]

    assert len(wg_no) > 0 and len(wg_rain) > 0, "Water Gun should appear"

    dmg_no = wg_no[0]["damage"]
    dmg_rain = wg_rain[0]["damage"]

    assert dmg_rain > dmg_no, (
        f"Water damage in rain ({dmg_rain}) should exceed normal ({dmg_no})"
    )


def test_critical_hit_deterministic():
    """Critical hits should be determined by the RNG (1 in 16 chance).

    Over many trials with different seeds, some should crit and some shouldn't.
    The same seed should always produce the same crit/no-crit outcome.
    """
    species_db = load_species_db(str(VISIBLE_DATA))
    moves_db = load_moves_db(str(VISIBLE_DATA))
    type_chart = load_type_chart(str(VISIBLE_DATA))

    crit_seeds = []
    no_crit_seeds = []

    for seed in range(200):
        scenario = {
            "seed": seed,
            "pokemon_1": {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]},
            "pokemon_2": {"species": "Eevee", "level": 50, "moves": ["Tackle"]},
            "move_choices": [{"pokemon_1": "Thunderbolt", "pokemon_2": "Tackle"}],
        }
        result = _make_scenario(scenario)
        turns = result["turns"]
        tb_actions = [t for t in turns if t.get("move") == "Thunderbolt"]
        if tb_actions and tb_actions[0].get("critical", False):
            crit_seeds.append(seed)
        else:
            no_crit_seeds.append(seed)

    # With 1/16 chance over 200 trials, expect ~12 crits
    assert len(crit_seeds) > 3, (
        f"Expected some critical hits (1/16 rate); got {len(crit_seeds)}/200"
    )
    assert len(no_crit_seeds) > 150, (
        f"Expected most non-crits; got {len(no_crit_seeds)}/200 non-crits"
    )

    # Deterministic: re-run a crit seed, should crit again
    if crit_seeds:
        seed = crit_seeds[0]
        scenario = {
            "seed": seed,
            "pokemon_1": {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]},
            "pokemon_2": {"species": "Eevee", "level": 50, "moves": ["Tackle"]},
            "move_choices": [{"pokemon_1": "Thunderbolt", "pokemon_2": "Tackle"}],
        }
        r1 = _make_scenario(scenario)
        r2 = _make_scenario(scenario)
        t1 = [t for t in r1["turns"] if t.get("move") == "Thunderbolt"][0]
        t2 = [t for t in r2["turns"] if t.get("move") == "Thunderbolt"][0]
        assert t1["critical"] == t2["critical"], "Crit outcome should be deterministic"


def test_trace_format_matches_spec():
    """Trace output should contain TURN headers and properly indented action lines."""
    scenario = {
        "seed": 42,
        "pokemon_1": {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]},
        "pokemon_2": {"species": "Squirtle", "level": 50, "moves": ["Water Gun"]},
        "move_choices": [
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"},
            {"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"},
        ],
    }
    result = _make_scenario(scenario, trace=True)

    assert "trace" in result, "Result must contain 'trace' key when trace=True"
    trace = result["trace"]
    assert isinstance(trace, list), "trace should be a list of strings"
    assert len(trace) > 0, "trace should not be empty"

    # Check for TURN headers
    turn_lines = [line for line in trace if line.startswith("TURN ")]
    assert len(turn_lines) >= 1, f"Expected TURN headers; got {turn_lines}"

    # Check for indented action lines
    action_lines = [line for line in trace if line.startswith("  ")]
    assert len(action_lines) >= 2, (
        f"Expected indented action lines; got {len(action_lines)}"
    )

    # Check that "used" appears (move usage lines)
    used_lines = [line for line in trace if "used" in line]
    assert len(used_lines) >= 1, "Expected 'used' in trace for move actions"

    # Check that damage/HP lines appear
    hp_lines = [line for line in trace if "HP:" in line]
    assert len(hp_lines) >= 1, "Expected HP status lines in trace"


def test_trace_deterministic_replay():
    """Running the same scenario with trace=True twice must produce
    identical trace output.
    """
    scenario = {
        "seed": 77,
        "pokemon_1": {"species": "Charmander", "level": 50, "moves": ["Flamethrower"]},
        "pokemon_2": {"species": "Bulbasaur", "level": 50, "moves": ["Vine Whip"]},
        "move_choices": [
            {"pokemon_1": "Flamethrower", "pokemon_2": "Vine Whip"},
            {"pokemon_1": "Flamethrower", "pokemon_2": "Vine Whip"},
        ],
    }

    result_1 = _make_scenario(scenario, trace=True)
    result_2 = _make_scenario(scenario, trace=True)

    assert result_1["trace"] == result_2["trace"], (
        "Trace output should be byte-identical across runs with same seed"
    )
    assert result_1["winner"] == result_2["winner"], "Winner should be deterministic"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
