"""Pokemon Sapphire constants: type chart, base stats, move data."""

# Type effectiveness chart: EFFECTIVENESS[attacking_type][defending_type] = multiplier
EFFECTIVENESS = {
    "Normal": {
        "Normal": 1.0, "Fire": 1.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 0.5, "Ghost": 0.0, "Dragon": 1.0,
        "Dark": 1.0, "Steel": 0.5,
    },
    "Fire": {
        "Normal": 1.0, "Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Electric": 1.0,
        "Ice": 2.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 2.0, "Rock": 0.5, "Ghost": 1.0, "Dragon": 0.5,
        "Dark": 1.0, "Steel": 2.0,
    },
    "Water": {
        "Normal": 1.0, "Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 2.0, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 2.0, "Ghost": 1.0, "Dragon": 0.5,
        "Dark": 1.0, "Steel": 1.0,
    },
    "Grass": {
        "Normal": 1.0, "Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5,
        "Psychic": 1.0, "Bug": 0.5, "Rock": 2.0, "Ghost": 1.0, "Dragon": 0.5,
        "Dark": 1.0, "Steel": 0.5,
    },
    "Electric": {
        "Normal": 1.0, "Fire": 1.0, "Water": 2.0, "Grass": 0.5, "Electric": 0.5,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 0.0, "Flying": 2.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 1.0, "Ghost": 1.0, "Dragon": 0.5,
        "Dark": 1.0, "Steel": 1.0,
    },
    "Ice": {
        "Normal": 1.0, "Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Electric": 1.0,
        "Ice": 0.5, "Fighting": 1.0, "Poison": 1.0, "Ground": 2.0, "Flying": 2.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 1.0, "Ghost": 1.0, "Dragon": 2.0,
        "Dark": 1.0, "Steel": 0.5,
    },
    "Fighting": {
        "Normal": 2.0, "Fire": 1.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 2.0, "Fighting": 1.0, "Poison": 0.5, "Ground": 1.0, "Flying": 0.5,
        "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dragon": 1.0,
        "Dark": 2.0, "Steel": 2.0,
    },
    "Poison": {
        "Normal": 1.0, "Fire": 1.0, "Water": 1.0, "Grass": 2.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 0.5, "Ground": 0.5, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 0.5, "Ghost": 0.5, "Dragon": 1.0,
        "Dark": 1.0, "Steel": 0.0,
    },
    "Ground": {
        "Normal": 1.0, "Fire": 2.0, "Water": 1.0, "Grass": 0.5, "Electric": 2.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 2.0, "Ground": 1.0, "Flying": 0.0,
        "Psychic": 1.0, "Bug": 0.5, "Rock": 2.0, "Ghost": 1.0, "Dragon": 1.0,
        "Dark": 1.0, "Steel": 2.0,
    },
    "Flying": {
        "Normal": 1.0, "Fire": 1.0, "Water": 1.0, "Grass": 2.0, "Electric": 0.5,
        "Ice": 1.0, "Fighting": 2.0, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 2.0, "Rock": 0.5, "Ghost": 1.0, "Dragon": 1.0,
        "Dark": 1.0, "Steel": 0.5,
    },
    "Psychic": {
        "Normal": 1.0, "Fire": 1.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 2.0, "Poison": 2.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 0.5, "Bug": 1.0, "Rock": 1.0, "Ghost": 1.0, "Dragon": 1.0,
        "Dark": 0.0, "Steel": 0.5,
    },
    "Bug": {
        "Normal": 1.0, "Fire": 0.5, "Water": 1.0, "Grass": 2.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 0.5, "Poison": 0.5, "Ground": 1.0, "Flying": 0.5,
        "Psychic": 2.0, "Bug": 1.0, "Rock": 1.0, "Ghost": 0.5, "Dragon": 1.0,
        "Dark": 2.0, "Steel": 0.5,
    },
    "Rock": {
        "Normal": 1.0, "Fire": 2.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 2.0, "Fighting": 0.5, "Poison": 1.0, "Ground": 0.5, "Flying": 2.0,
        "Psychic": 1.0, "Bug": 2.0, "Rock": 1.0, "Ghost": 1.0, "Dragon": 1.0,
        "Dark": 1.0, "Steel": 0.5,
    },
    "Ghost": {
        "Normal": 0.0, "Fire": 1.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 2.0, "Bug": 1.0, "Rock": 1.0, "Ghost": 2.0, "Dragon": 1.0,
        "Dark": 0.5, "Steel": 1.0,
    },
    "Dragon": {
        "Normal": 1.0, "Fire": 1.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 1.0, "Ghost": 1.0, "Dragon": 2.0,
        "Dark": 1.0, "Steel": 0.5,
    },
    "Dark": {
        "Normal": 1.0, "Fire": 1.0, "Water": 1.0, "Grass": 1.0, "Electric": 1.0,
        "Ice": 1.0, "Fighting": 0.5, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 2.0, "Bug": 1.0, "Rock": 1.0, "Ghost": 2.0, "Dragon": 1.0,
        "Dark": 0.5, "Steel": 0.5,
    },
    "Steel": {
        "Normal": 1.0, "Fire": 0.5, "Water": 0.5, "Grass": 1.0, "Electric": 0.5,
        "Ice": 2.0, "Fighting": 1.0, "Poison": 1.0, "Ground": 1.0, "Flying": 1.0,
        "Psychic": 1.0, "Bug": 1.0, "Rock": 2.0, "Ghost": 1.0, "Dragon": 1.0,
        "Dark": 1.0, "Steel": 0.5,
    },
}

# Species data: base stats and types
# Format: {species: {"types": [...], "base_hp": N, "base_atk": N, ...}}
SPECIES_DATA = {
    "Blaziken": {
        "types": ["Fire", "Fighting"],
        "base_hp": 80, "base_atk": 120, "base_def": 70,
        "base_spa": 110, "base_spd": 70, "base_spe": 80,
    },
    "Swampert": {
        "types": ["Water", "Ground"],
        "base_hp": 100, "base_atk": 110, "base_def": 90,
        "base_spa": 85, "base_spd": 90, "base_spe": 60,
    },
    "Sceptile": {
        "types": ["Grass"],
        "base_hp": 70, "base_atk": 85, "base_def": 65,
        "base_spa": 105, "base_spd": 85, "base_spe": 120,
    },
    "Makuhita": {
        "types": ["Fighting"],
        "base_hp": 72, "base_atk": 60, "base_def": 30,
        "base_spa": 20, "base_spd": 30, "base_spe": 25,
    },
    "Hariyama": {
        "types": ["Fighting"],
        "base_hp": 144, "base_atk": 120, "base_def": 60,
        "base_spa": 40, "base_spd": 60, "base_spe": 50,
    },
    "Meditite": {
        "types": ["Fighting", "Psychic"],
        "base_hp": 30, "base_atk": 40, "base_def": 55,
        "base_spa": 40, "base_spd": 55, "base_spe": 60,
    },
    "Machop": {
        "types": ["Fighting"],
        "base_hp": 70, "base_atk": 80, "base_def": 50,
        "base_spa": 35, "base_spd": 35, "base_spe": 35,
    },
    "Wingull": {
        "types": ["Water", "Flying"],
        "base_hp": 40, "base_atk": 30, "base_def": 30,
        "base_spa": 55, "base_spd": 30, "base_spe": 85,
    },
    "Pelipper": {
        "types": ["Water", "Flying"],
        "base_hp": 60, "base_atk": 50, "base_def": 100,
        "base_spa": 85, "base_spd": 70, "base_spe": 65,
    },
    "Tentacool": {
        "types": ["Water", "Poison"],
        "base_hp": 40, "base_atk": 40, "base_def": 35,
        "base_spa": 50, "base_spd": 100, "base_spe": 70,
    },
    "Geodude": {
        "types": ["Rock", "Ground"],
        "base_hp": 40, "base_atk": 80, "base_def": 100,
        "base_spa": 30, "base_spd": 30, "base_spe": 20,
    },
    "Zubat": {
        "types": ["Poison", "Flying"],
        "base_hp": 40, "base_atk": 45, "base_def": 35,
        "base_spa": 30, "base_spd": 40, "base_spe": 55,
    },
    "Ralts": {
        "types": ["Psychic"],
        "base_hp": 28, "base_atk": 25, "base_def": 25,
        "base_spa": 45, "base_spd": 35, "base_spe": 40,
    },
    "Aron": {
        "types": ["Steel", "Rock"],
        "base_hp": 50, "base_atk": 70, "base_def": 100,
        "base_spa": 40, "base_spd": 40, "base_spe": 30,
    },
    "Poochyena": {
        "types": ["Dark"],
        "base_hp": 35, "base_atk": 55, "base_def": 35,
        "base_spa": 30, "base_spd": 30, "base_spe": 35,
    },
    "Shroomish": {
        "types": ["Grass"],
        "base_hp": 60, "base_atk": 40, "base_def": 60,
        "base_spa": 40, "base_spd": 60, "base_spe": 35,
    },
    "Nuzleaf": {
        "types": ["Grass", "Dark"],
        "base_hp": 70, "base_atk": 70, "base_def": 40,
        "base_spa": 60, "base_spd": 40, "base_spe": 60,
    },
}

# Move data: {name: {"type": T, "category": "physical"/"special"/"status",
#              "power": N, "accuracy": N, "pp": N, "priority": N, "effect": ...}}
MOVE_DATA = {
    "Blaze Kick": {
        "type": "Fire", "category": "physical", "power": 85, "accuracy": 90,
        "pp": 10, "priority": 0, "effect": None,
    },
    "Double Kick": {
        "type": "Fighting", "category": "physical", "power": 30, "accuracy": 100,
        "pp": 30, "priority": 0, "effect": "hit_twice",
    },
    "Peck": {
        "type": "Flying", "category": "physical", "power": 35, "accuracy": 100,
        "pp": 35, "priority": 0, "effect": None,
    },
    "Bulk Up": {
        "type": "Fighting", "category": "status", "power": 0, "accuracy": 100,
        "pp": 20, "priority": 0, "effect": "boost_atk_def",
    },
    "Arm Thrust": {
        "type": "Fighting", "category": "physical", "power": 15, "accuracy": 100,
        "pp": 20, "priority": 0, "effect": "hit_2_to_5",
    },
    "Vital Throw": {
        "type": "Fighting", "category": "physical", "power": 70, "accuracy": 100,
        "pp": 10, "priority": -1, "effect": None,
    },
    "Sand Attack": {
        "type": "Ground", "category": "status", "power": 0, "accuracy": 100,
        "pp": 15, "priority": 0, "effect": "lower_accuracy",
    },
    "Tackle": {
        "type": "Normal", "category": "physical", "power": 40, "accuracy": 100,
        "pp": 35, "priority": 0, "effect": None,
    },
    "Water Gun": {
        "type": "Water", "category": "special", "power": 40, "accuracy": 100,
        "pp": 25, "priority": 0, "effect": None,
    },
    "Ember": {
        "type": "Fire", "category": "special", "power": 40, "accuracy": 100,
        "pp": 25, "priority": 0, "effect": None,
    },
    "Razor Leaf": {
        "type": "Grass", "category": "physical", "power": 55, "accuracy": 95,
        "pp": 25, "priority": 0, "effect": None,
    },
    "Quick Attack": {
        "type": "Normal", "category": "physical", "power": 40, "accuracy": 100,
        "pp": 30, "priority": 1, "effect": None,
    },
    "Confusion": {
        "type": "Psychic", "category": "special", "power": 50, "accuracy": 100,
        "pp": 25, "priority": 0, "effect": None,
    },
    "Rock Tomb": {
        "type": "Rock", "category": "physical", "power": 60, "accuracy": 95,
        "pp": 15, "priority": 0, "effect": "lower_speed",
    },
    "Mud Shot": {
        "type": "Ground", "category": "special", "power": 55, "accuracy": 95,
        "pp": 15, "priority": 0, "effect": "lower_speed",
    },
    "Bite": {
        "type": "Dark", "category": "physical", "power": 60, "accuracy": 100,
        "pp": 25, "priority": 0, "effect": None,
    },
    "Wing Attack": {
        "type": "Flying", "category": "physical", "power": 60, "accuracy": 100,
        "pp": 35, "priority": 0, "effect": None,
    },
    "Poison Sting": {
        "type": "Poison", "category": "physical", "power": 15, "accuracy": 100,
        "pp": 35, "priority": 0, "effect": "may_poison",
    },
    "Absorb": {
        "type": "Grass", "category": "special", "power": 20, "accuracy": 100,
        "pp": 25, "priority": 0, "effect": "drain_half",
    },
    "Thundershock": {
        "type": "Electric", "category": "special", "power": 40, "accuracy": 100,
        "pp": 30, "priority": 0, "effect": None,
    },
    "Focus Energy": {
        "type": "Normal", "category": "status", "power": 0, "accuracy": 100,
        "pp": 30, "priority": 0, "effect": "boost_crit",
    },
    "Karate Chop": {
        "type": "Fighting", "category": "physical", "power": 50, "accuracy": 100,
        "pp": 25, "priority": 0, "effect": None,
    },
    "Potion": {
        "type": "Normal", "category": "status", "power": 0, "accuracy": 100,
        "pp": 99, "priority": 0, "effect": "heal_20",
    },
    "Super Potion": {
        "type": "Normal", "category": "status", "power": 0, "accuracy": 100,
        "pp": 99, "priority": 0, "effect": "heal_50",
    },
}

# Stat stage multipliers (Gen III): stage -> multiplier (numerator/denominator)
STAT_STAGE_MULTIPLIERS = {
    -6: (2, 8), -5: (2, 7), -4: (2, 6), -3: (2, 5),
    -2: (2, 4), -1: (2, 3), 0: (2, 2), 1: (3, 2),
    2: (4, 2), 3: (5, 2), 4: (6, 2), 5: (7, 2), 6: (8, 2),
}


def get_type_effectiveness(move_type: str, defender_types: list[str]) -> float:
    """Calculate type effectiveness multiplier for move vs defender types."""
    multiplier = 1.0
    for def_type in defender_types:
        if move_type in EFFECTIVENESS and def_type in EFFECTIVENESS[move_type]:
            multiplier *= EFFECTIVENESS[move_type][def_type]
    return multiplier


def get_stat_multiplier(stage: int) -> float:
    """Return the stat multiplier for a given stat stage."""
    stage = max(-6, min(6, stage))
    num, den = STAT_STAGE_MULTIPLIERS[stage]
    return num / den
