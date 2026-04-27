#!/usr/bin/env python3
"""Pokemon-style text battle engine.

Executes deterministic 1v1 battles loaded from scenario JSON files.
Produces structured JSON output with winner, turn log, and final state.
"""

import json
import math
import random
import sys
from pathlib import Path

from models import Pokemon, Move, BattleState, TurnResult


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def load_json(path):
    """Load and return parsed JSON from *path*."""
    with open(path) as f:
        return json.load(f)


def load_species_db(data_dir=None):
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    return load_json(data_dir / "species.json")


def load_moves_db(data_dir=None):
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    return load_json(data_dir / "moves.json")


def load_type_chart(data_dir=None):
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    return load_json(data_dir / "type_chart.json")


# ---------------------------------------------------------------------------
# Stat calculation
# ---------------------------------------------------------------------------

def calculate_stat(base, level, iv=0, ev=0, is_hp=False):
    """Standard Pokemon stat formula (simplified, no nature).

    HP  = floor((2*base + iv + ev/4) * level / 100) + level + 10
    Other = floor((2*base + iv + ev/4) * level / 100) + 5
    """
    return int(((2 * base + iv + ev // 4) * level / 100) + 5)


# ---------------------------------------------------------------------------
# Pokemon creation
# ---------------------------------------------------------------------------

def create_pokemon(species_name, level, move_names, species_db, moves_db):
    """Create a Pokemon instance from species data and move list."""
    spec = species_db[species_name]
    stats = {}
    for stat_name, base_val in spec["stats"].items():
        stats[stat_name] = calculate_stat(
            base_val, level, is_hp=(stat_name == "hp"),
        )

    moves = []
    for name in move_names:
        m = moves_db[name]
        moves.append(Move(
            name=name,
            type=m["type"],
            category=m["category"],
            power=m["power"],
            accuracy=m["accuracy"],
            pp=m["pp"],
            current_pp=m["pp"],
            priority=m.get("priority", 0),
            effect=m.get("effect"),
        ))

    return Pokemon(
        name=species_name,
        types=spec["types"],
        stats=stats,
        moves=moves,
        current_hp=stats["hp"],
        status=None,
        stat_stages={
            "attack": 0, "defense": 0,
            "sp_atk": 0, "sp_def": 0, "speed": 0,
        },
    )


# ---------------------------------------------------------------------------
# Type effectiveness
# ---------------------------------------------------------------------------

def get_type_effectiveness(move_type, defender_types, type_chart):
    """Return the combined type-effectiveness multiplier.

    Looks up each defender type in the chart and multiplies together.
    Missing entries default to 1.0 (neutral).
    """
    multiplier = 1.0
    for def_type in defender_types:
        if def_type in type_chart and move_type in type_chart[def_type]:
            multiplier *= type_chart[def_type][move_type]
    return multiplier


# ---------------------------------------------------------------------------
# Damage calculation
# ---------------------------------------------------------------------------

def calculate_damage(attacker, defender, move, type_chart, rng, rand_factor=None):
    """Calculate damage for a single attack.

    Uses the standard Pokemon damage formula at a fixed level of 50:
      base = ((2*level/5 + 2) * power * A / D) / 50 + 2
      damage = base * STAB * type_effectiveness * random_factor

    Returns 0 for status moves or immune matchups.
    """
    if move.category == "status":
        return 0

    level = 50

    if move.category == "physical":
        atk_stat = attacker.stats["attack"]
        def_stat = defender.stats["defense"]
        atk_stage = attacker.stat_stages.get("attack", 0)
        def_stage = defender.stat_stages.get("defense", 0)
    else:  # special
        atk_stat = attacker.stats["sp_atk"]
        def_stat = defender.stats["sp_def"]
        atk_stage = attacker.stat_stages.get("sp_atk", 0)
        def_stage = defender.stat_stages.get("sp_def", 0)

    # Apply stat stage modifiers
    if atk_stage != 0:
        atk_stat = int(atk_stat * (1.0 + atk_stage * 0.25))
    if def_stage != 0:
        def_stat = int(def_stat * (1.0 + def_stage * 0.25))

    # Base damage formula
    base = ((2 * level / 5 + 2) * move.power * atk_stat / def_stat) / 50 + 2

    # Same-Type Attack Bonus (STAB)
    stab = 1.5 if move.type in attacker.types else 1.0

    # Type effectiveness
    effectiveness = get_type_effectiveness(move.type, defender.types, type_chart)

    modifier = stab + effectiveness

    # Random factor 85-100%
    if rand_factor is None:
        rand_factor = rng.randint(85, 100) / 100.0

    damage = int(base * modifier * rand_factor)

    # Immune matchups always deal 0; otherwise minimum 1 damage
    if effectiveness == 0:
        return 0
    return max(1, damage)


# ---------------------------------------------------------------------------
# Turn order
# ---------------------------------------------------------------------------

def determine_turn_order(pokemon_1, pokemon_2, move_1, move_2, rng):
    """Decide which Pokemon attacks first.

    Priority moves go first. Among equal priority, the faster Pokemon moves
    first. Ties are broken by a deterministic coin flip from the RNG.

    Returns (1, 2) if pokemon_1 goes first, (2, 1) otherwise.
    """
    # Check move priority first
    if move_1.priority != move_2.priority:
        return (1, 2) if move_1.priority > move_2.priority else (2, 1)

    speed_1 = pokemon_1.stats["speed"]
    speed_2 = pokemon_2.stats["speed"]

    if speed_1 < speed_2:
        return (1, 2)
    elif speed_2 < speed_1:
        return (2, 1)
    else:
        # Speed tie — deterministic RNG tiebreak
        return (1, 2) if rng.random() < 0.5 else (2, 1)


# ---------------------------------------------------------------------------
# Attack execution
# ---------------------------------------------------------------------------

def execute_attack(attacker, defender, move, type_chart, rng):
    """Execute one attack from *attacker* against *defender*.

    Handles PP deduction, accuracy check, damage calculation.
    Returns a TurnResult describing what happened.
    """
    # Out of PP — use Struggle (self-damage, but simplified here to 0)
    if move.current_pp <= 0:
        return TurnResult(
            attacker=attacker.name,
            move="Struggle",
            damage=0,
            defender_hp_after=defender.current_hp,
            effectiveness="normal",
            critical=False,
            message=f"{attacker.name} has no PP for {move.name} and used Struggle!",
        )

    move.current_pp -= 1

    # Pre-compute random damage factor before accuracy check
    damage_rand = rng.randint(85, 100) / 100.0

    # Accuracy check
    if rng.randint(1, 100) > move.accuracy:
        return TurnResult(
            attacker=attacker.name,
            move=move.name,
            damage=0,
            defender_hp_after=defender.current_hp,
            effectiveness="miss",
            critical=False,
            message=f"{attacker.name}'s {move.name} missed!",
        )

    # Status moves (step 1 placeholder — just report, no state change)
    if move.category == "status":
        return TurnResult(
            attacker=attacker.name,
            move=move.name,
            damage=0,
            defender_hp_after=defender.current_hp,
            effectiveness="status",
            critical=False,
            message=f"{attacker.name} used {move.name}!",
        )

    # Damage calculation (pass pre-computed random factor)
    damage = calculate_damage(attacker, defender, move, type_chart, rng, damage_rand)
    effectiveness = get_type_effectiveness(move.type, defender.types, type_chart)

    # Apply damage to defender
    defender.current_hp = max(0, defender.current_hp - damage)

    # Determine effectiveness label
    if effectiveness > 1.0:
        eff_label = "super_effective"
    elif effectiveness == 0:
        eff_label = "immune"
    elif effectiveness < 1.0:
        eff_label = "not_very_effective"
    else:
        eff_label = "normal"

    msg = f"{attacker.name} used {move.name}! ({eff_label}, {damage} dmg)"
    return TurnResult(
        attacker=attacker.name,
        move=move.name,
        damage=damage,
        defender_hp_after=defender.current_hp,
        effectiveness=eff_label,
        critical=False,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Main battle loop
# ---------------------------------------------------------------------------

def run_battle(scenario_path, data_dir=None):
    """Load a scenario and execute the battle.

    Args:
        scenario_path: Path to a scenario JSON file.
        data_dir: Optional path to the data directory containing species.json,
                  moves.json, and type_chart.json.

    Returns a dict:
        {
            "winner": str or None,
            "turns": [ {attacker, move, damage, defender_hp_after, ...}, ... ],
            "final_state": {
                "pokemon_1": {"name": str, "hp": int, "max_hp": int},
                "pokemon_2": {"name": str, "hp": int, "max_hp": int},
            }
        }
    """
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    scenario = load_json(scenario_path)
    species_db = load_species_db(data_dir)
    moves_db = load_moves_db(data_dir)
    type_chart = load_type_chart(data_dir)

    rng = random.Random(scenario["seed"])

    # Create Pokemon
    p1_conf = scenario["pokemon_1"]
    p2_conf = scenario["pokemon_2"]

    pokemon_1 = create_pokemon(
        p1_conf["species"],
        p1_conf.get("level", 50),
        p1_conf["moves"],
        species_db,
        moves_db,
    )
    pokemon_2 = create_pokemon(
        p2_conf["species"],
        p2_conf.get("level", 50),
        p2_conf["moves"],
        species_db,
        moves_db,
    )

    turns = []
    max_turns = scenario.get("max_turns", 100)

    for turn_num in range(1, max_turns + 1):
        # Determine moves for this turn
        if "move_choices" in scenario:
            if turn_num - 1 >= len(scenario["move_choices"]):
                break
            choices = scenario["move_choices"][turn_num - 1]
            move_1_name = choices["pokemon_1"]
            move_2_name = choices["pokemon_2"]
            move_1 = next(
                (m for m in pokemon_1.moves if m.name == move_1_name), None,
            )
            move_2 = next(
                (m for m in pokemon_2.moves if m.name == move_2_name), None,
            )
            if move_1 is None or move_2 is None:
                break
        else:
            # Auto-select: first move with PP remaining
            move_1 = next(
                (m for m in pokemon_1.moves if m.current_pp > 0), None,
            )
            move_2 = next(
                (m for m in pokemon_2.moves if m.current_pp > 0), None,
            )
            if move_1 is None or move_2 is None:
                break

        # Determine attack order
        order = determine_turn_order(pokemon_1, pokemon_2, move_1, move_2, rng)

        if order == (1, 2):
            first_atk, first_def, first_move = pokemon_1, pokemon_2, move_1
            second_atk, second_def, second_move = pokemon_2, pokemon_1, move_2
        else:
            first_atk, first_def, first_move = pokemon_2, pokemon_1, move_2
            second_atk, second_def, second_move = pokemon_1, pokemon_2, move_1

        # First Pokemon attacks
        result_1 = execute_attack(
            first_atk, first_def, first_move, type_chart, rng,
        )
        turns.append(result_1.__dict__)

        # Second Pokemon attacks
        result_2 = execute_attack(
            second_atk, second_def, second_move, type_chart, rng,
        )
        turns.append(result_2.__dict__)

        # Check for faints at the end of the turn
        if pokemon_1.current_hp <= 0 or pokemon_2.current_hp <= 0:
            break

    # Determine winner
    winner = None
    if pokemon_1.current_hp <= 0 and pokemon_2.current_hp <= 0:
        # Both fainted (only possible with bug 5) — first to faint loses
        winner = None  # draw
    elif pokemon_1.current_hp <= 0:
        winner = pokemon_2.name
    elif pokemon_2.current_hp <= 0:
        winner = pokemon_1.name

    return {
        "winner": winner,
        "turns": turns,
        "final_state": {
            "pokemon_1": {
                "name": pokemon_1.name,
                "hp": pokemon_1.current_hp,
                "max_hp": pokemon_1.stats["hp"],
            },
            "pokemon_2": {
                "name": pokemon_2.name,
                "hp": pokemon_2.current_hp,
                "max_hp": pokemon_2.stats["hp"],
            },
        },
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 battle_engine.py <scenario.json> [data_dir]")
        sys.exit(1)

    scenario_path = sys.argv[1]
    data_dir = sys.argv[2] if len(sys.argv) > 2 else None

    result = run_battle(scenario_path, data_dir)
    print(json.dumps(result, indent=2))
