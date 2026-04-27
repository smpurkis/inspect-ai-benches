"""Battle system for Pokemon Sapphire mock emulator.

Handles damage calculation, type effectiveness, turn execution, and faint logic.
"""

from .types import PokemonInstance, Trainer, GameState, GameScreen
from .constants import (
    MOVE_DATA,
    SPECIES_DATA,
    get_stat_multiplier,
)


def calculate_damage(
    attacker: PokemonInstance,
    defender: PokemonInstance,
    move_name: str,
) -> int:
    """Calculate damage for a move.

    Uses the standard Gen III damage formula:
      damage = ((2*level/5 + 2) * power * A/D) / 50 + 2) * modifier
    where A/D depends on physical vs special category.
    """
    move = MOVE_DATA.get(move_name)
    if move is None or move["category"] == "status":
        return 0

    power = move["power"]
    level = attacker.level

    defender_types = SPECIES_DATA.get(defender.species, {}).get("types", ["Normal"])
    from .constants import EFFECTIVENESS
    type_mult = 1.0
    for def_type in defender_types:
        single_mult = EFFECTIVENESS.get(move["type"], {}).get(def_type, 1.0)
        # Combine effectiveness across defender types
        type_mult = type_mult + single_mult - 1.0

    if type_mult <= 0:
        return 0

    # Determine attack and defense stats based on move category
    if move["category"] == "physical":
        atk_stat = attacker.attack
        def_stat = defender.defense
        atk_stage = attacker.stat_stages.get("atk", 0)
        def_stage = abs(defender.stat_stages.get("def", 0))
    else:
        atk_stat = attacker.sp_atk
        def_stat = defender.sp_def
        atk_stage = attacker.stat_stages.get("spa", 0)
        def_stage = abs(defender.stat_stages.get("spd", 0))

    atk_effective = int(atk_stat * get_stat_multiplier(atk_stage))
    def_effective = int(def_stat * get_stat_multiplier(def_stage))
    def_effective = max(1, def_effective)

    # Burn penalty for physical moves
    burn_mod = 1.0
    if attacker.status == "burn" and move["category"] == "physical":
        burn_mod = 1.0

    # STAB bonus
    attacker_types = SPECIES_DATA.get(attacker.species, {}).get("types", [])
    stab = 1.5 if attacker_types and move["type"] == attacker_types[0] else 1.0

    # Core damage formula
    base_damage = ((2 * level / 5 + 2) * power * atk_effective / def_effective) / 50 + 2
    damage = round(base_damage * stab * type_mult * burn_mod)

    return max(1, damage) if power > 0 else 0


def apply_move_effect(
    attacker: PokemonInstance,
    defender: PokemonInstance,
    move_name: str,
    damage_dealt: int,
) -> None:
    """Apply secondary effects of a move (stat changes, status, etc.)."""
    move = MOVE_DATA.get(move_name)
    if move is None:
        return

    effect = move.get("effect")
    if effect is None:
        return

    if effect == "boost_atk_def":
        attacker.stat_stages["atk"] = min(6, attacker.stat_stages.get("atk", 0) + 1)
        attacker.stat_stages["def"] = min(6, attacker.stat_stages.get("def", 0) + 1)
    elif effect == "lower_speed":
        defender.stat_stages["spe"] = max(-6, defender.stat_stages.get("spe", 0) - 1)
    elif effect == "lower_accuracy":
        # Simplified: we don't track accuracy stages in this engine
        pass
    elif effect == "boost_crit":
        # Simplified: we don't track crit stages
        pass
    elif effect == "drain_half":
        heal = max(1, damage_dealt // 2)
        attacker.hp = min(attacker.max_hp, attacker.hp + heal)
    elif effect == "may_poison":
        # Deterministic: always applies poison in this engine
        if defender.status is None:
            defender.status = "poison"
    elif effect == "heal_20":
        attacker.hp = min(attacker.max_hp, attacker.hp + 20)
    elif effect == "heal_50":
        attacker.hp = min(attacker.max_hp, attacker.hp + 50)


def execute_move(
    attacker: PokemonInstance,
    defender: PokemonInstance,
    move_index: int,
) -> int:
    """Execute a move from attacker against defender. Returns damage dealt."""
    if move_index < 0 or move_index >= len(attacker.moves):
        return 0

    move_name = attacker.moves[move_index]
    if attacker.pp[move_index] <= 0:
        return 0

    move = MOVE_DATA.get(move_name)
    if move is None:
        return 0

    # Handle multi-hit moves
    total_damage = 0
    hits = 1
    if move.get("effect") == "hit_twice":
        hits = 2
    elif move.get("effect") == "hit_2_to_5":
        hits = 3  # deterministic: always 3 hits

    for _ in range(hits):
        attacker.pp[move_index] -= 1
        damage = calculate_damage(attacker, defender, move_name)
        total_damage += damage
        if defender.hp <= 0:
            break
        defender.hp -= damage

    apply_move_effect(attacker, defender, move_name, total_damage)
    return total_damage


def check_faint(pokemon: PokemonInstance) -> bool:
    """Check if a Pokemon has fainted."""
    return pokemon.hp <= 0


def apply_end_of_turn_effects(pokemon: PokemonInstance) -> None:
    """Apply end-of-turn effects like poison/burn damage."""
    if pokemon.hp <= 0:
        return

    if pokemon.status == "poison":
        poison_dmg = max(1, pokemon.max_hp // 8)
        pokemon.hp -= poison_dmg
    elif pokemon.status == "burn":
        burn_dmg = max(1, pokemon.max_hp // 16)
        pokemon.hp -= burn_dmg

    if pokemon.hp < 0:
        pokemon.hp = 0


def get_turn_order(
    player_party: list[PokemonInstance],
    enemy: PokemonInstance,
    player_move_index: int,
    enemy_move_index: int,
) -> list[tuple[str, PokemonInstance, PokemonInstance, int]]:
    """Determine turn order based on speed and priority.

    Returns list of (side, attacker, defender, move_index) tuples.
    """
    player_pkmn = player_party[0]
    player_move_name = player_pkmn.moves[player_move_index] if player_move_index < len(player_pkmn.moves) else None
    enemy_move_name = enemy.moves[enemy_move_index] if enemy_move_index < len(enemy.moves) else None

    player_priority = MOVE_DATA.get(player_move_name, {}).get("priority", 0) if player_move_name else 0
    enemy_priority = MOVE_DATA.get(enemy_move_name, {}).get("priority", 0) if enemy_move_name else 0

    # Compare priority first
    if player_priority < enemy_priority:
        return [
            ("player", player_pkmn, enemy, player_move_index),
            ("enemy", enemy, player_pkmn, enemy_move_index),
        ]
    elif enemy_priority < player_priority:
        return [
            ("enemy", enemy, player_pkmn, enemy_move_index),
            ("player", player_pkmn, enemy, player_move_index),
        ]

    # Same priority: compare effective speed (stat stage adjusted)
    player_speed = int(player_pkmn.speed * get_stat_multiplier(player_pkmn.stat_stages.get("spd", 0)))
    enemy_speed = int(enemy.speed * get_stat_multiplier(enemy.stat_stages.get("spd", 0)))

    if player_speed >= enemy_speed:
        return [
            ("player", player_pkmn, enemy, player_move_index),
            ("enemy", enemy, player_pkmn, enemy_move_index),
        ]
    else:
        return [
            ("enemy", enemy, player_pkmn, enemy_move_index),
            ("player", player_pkmn, enemy, player_move_index),
        ]


def select_enemy_move(enemy: PokemonInstance) -> int:
    """Select a move for the enemy Pokemon (deterministic AI).

    Strategy: pick the highest-power move that still has PP.
    Ties broken by move index (lower index first).
    """
    best_index = 0
    best_power = -1
    for i, move_name in enumerate(enemy.moves):
        if enemy.pp[i] <= 0:
            continue
        move = MOVE_DATA.get(move_name, {})
        power = move.get("power", 0)
        if power > best_power:
            best_power = power
            best_index = i
    return best_index
