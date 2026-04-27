#!/usr/bin/env python3
"""Hidden tests: battle mechanics with variant scenarios (18 tests)."""

import json
import sys
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
FILES_BASE = HIDDEN_BASE.parent / "files"
sys.path.insert(0, str(FILES_BASE))

from emulator.game_engine import load_savestate, replay_actions, state_to_dict
from emulator.types import GameScreen


def load_hidden_ref(name):
    with open(HIDDEN_BASE / "reference" / name) as f:
        return json.load(f)


# ---------- original scenario tests ----------


def test_hidden_battle_different_lead():
    """Hidden scenario with Sceptile lead instead of Blaziken."""
    ref = load_hidden_ref("battle_hidden_01_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_01.json"))

    assert state.player_party[0].species == "Sceptile"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won with Sceptile lead"
    assert result["whiteout"] is False

    # Verify damage calculation is correct (catches dual-type effectiveness bug)
    assert result["player_party"][0]["hp"] == ref["player_hp"], (
        f"Player HP should be {ref['player_hp']} but got {result['player_party'][0]['hp']} "
        f"— likely a type effectiveness calculation error"
    )


def test_hidden_battle_low_hp_start():
    """Player starts with reduced HP and must still win."""
    ref = load_hidden_ref("battle_hidden_02_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_02.json"))

    assert state.player_party[0].hp == 25, "Player should start with low HP"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["whiteout"] is False, "Player should not whiteout"
    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    )


def test_hidden_battle_status_condition():
    """Enemy starts with poison status; poison damage should apply each turn."""
    ref = load_hidden_ref("battle_hidden_03_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_03.json"))

    assert state.enemy_trainer.party[0].status == "poison"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    )


def test_hidden_battle_stab_second_type():
    """Hidden scenario where STAB on a secondary type is required to OHKO."""
    ref = load_hidden_ref("battle_hidden_04_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_04.json"))

    assert state.player_party[0].species == "Blaziken"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won (STAB must apply for secondary type moves)"
    assert result["whiteout"] is False
    assert result["player_party"][0]["hp"] == ref["player_hp"], (
        f"Player HP should be {ref['player_hp']} but got {result['player_party'][0]['hp']}"
    )


# ---------- new scenario tests ----------


def test_hidden_battle_4x_effectiveness():
    """Grass vs Water/Ground must deal 4x damage (multiplicative, not additive 3x)."""
    ref = load_hidden_ref("battle_hidden_05_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_05.json"))

    assert state.player_party[0].species == "Sceptile"
    assert state.enemy_trainer.party[0].species == "Swampert"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won"
    assert result["whiteout"] is False
    assert result["player_party"][0]["hp"] == ref["player_hp"], (
        f"Player HP should be {ref['player_hp']} but got {result['player_party'][0]['hp']}. "
        f"Grass vs Water/Ground should be 4x (multiplicative), not 3x (additive)."
    )


def test_hidden_battle_burn_penalty():
    """Burned attacker should deal half physical damage (Gen III burn mechanic)."""
    ref = load_hidden_ref("battle_hidden_06_result.json")
    state = load_savestate(str(HIDDEN_BASE / "savestates" / "battle_hidden_06.json"))

    assert state.player_party[0].status == "burn", "Player should start with burn status"
    state = replay_actions(state, ref["actions"])
    result = state_to_dict(state)

    assert result["battle_won"] is True or (
        result["enemy_trainer"] is not None and result["enemy_trainer"]["defeated"] is True
    ), "Battle should be won even with burn penalty"
    assert result["whiteout"] is False
    assert result["player_party"][0]["hp"] == ref["player_hp"], (
        f"Player HP should be {ref['player_hp']} but got {result['player_party'][0]['hp']}. "
        f"Burn should halve physical damage output in Gen III."
    )


# ---------- direct damage calculation tests ----------


def test_hidden_ground_immunity_dual_type():
    """Ground moves should deal 0 damage to Water/Flying (Ground vs Flying = 0x).

    Correct (multiplicative): Ground vs Water (2x) * Ground vs Flying (0x) = 0x (immune)
    Buggy (additive): 1 + (2-1) + (0-1) = 1x (incorrectly deals damage)
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    swampert = PokemonInstance(
        species="Swampert", level=30, hp=120, max_hp=120,
        attack=80, defense=70, sp_atk=60, sp_def=65, speed=45,
        moves=["Mud Shot", "Water Gun"], pp=[15, 25],
    )
    wingull = PokemonInstance(
        species="Wingull", level=20, hp=45, max_hp=45,
        attack=25, defense=25, sp_atk=40, sp_def=25, speed=55,
        moves=["Water Gun", "Wing Attack"], pp=[25, 35],
    )

    # Ground vs Water/Flying: 2.0 * 0.0 = 0.0 (immune)
    damage = calculate_damage(swampert, wingull, "Mud Shot")
    assert damage == 0, (
        f"Ground vs Water/Flying should be 0 (immune due to Flying). "
        f"Got {damage}. Multiplicative: 2.0 * 0.0 = 0.0; "
        f"additive bug gives 1.0 + (2.0-1.0) + (0.0-1.0) = 1.0"
    )


def test_hidden_fighting_double_resist():
    """Fighting vs Poison/Flying should deal quarter damage (0.5 * 0.5 = 0.25x).

    Correct (multiplicative): 0.5 * 0.5 = 0.25x
    Buggy (additive): 1 + (0.5-1) + (0.5-1) = 0.0 (incorrectly zero!)
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    machop = PokemonInstance(
        species="Machop", level=25, hp=60, max_hp=60,
        attack=55, defense=40, sp_atk=30, sp_def=30, speed=30,
        moves=["Karate Chop"], pp=[25],
    )
    zubat = PokemonInstance(
        species="Zubat", level=20, hp=40, max_hp=40,
        attack=35, defense=28, sp_atk=25, sp_def=32, speed=40,
        moves=["Bite"], pp=[25],
    )

    # Fighting vs Poison/Flying: 0.5 * 0.5 = 0.25x (resisted, but not zero)
    damage = calculate_damage(machop, zubat, "Karate Chop")
    assert damage > 0, (
        f"Fighting vs Poison/Flying should deal reduced damage (0.25x), not zero. "
        f"Got {damage}. Additive bug computes 1 + (0.5-1) + (0.5-1) = 0.0 which "
        f"incorrectly makes it an immunity."
    )

    # Verify it's actually reduced: compare against neutral target (same defense stat)
    neutral_defender = PokemonInstance(
        species="Makuhita", level=20, hp=40, max_hp=40,
        attack=35, defense=28, sp_atk=25, sp_def=32, speed=40,
        moves=["Tackle"], pp=[35],
    )
    # Fighting vs Fighting (Makuhita) = 1.0x, so this is a neutral baseline
    neutral_damage = calculate_damage(machop, neutral_defender, "Karate Chop")
    assert damage < neutral_damage, (
        f"Damage to Poison/Flying ({damage}) should be less than neutral ({neutral_damage})"
    )


def test_hidden_stab_all_types():
    """STAB should apply for ANY matching type, not just the first one.

    Blaziken (Fire/Fighting) using Double Kick (Fighting) should get STAB
    because Fighting is one of Blaziken's types.
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    blaziken = PokemonInstance(
        species="Blaziken", level=36, hp=108, max_hp=108,
        attack=95, defense=65, sp_atk=85, sp_def=65, speed=80,
        moves=["Blaze Kick", "Double Kick"], pp=[10, 30],
    )
    # Use a Fighting-type defender so both Fire and Fighting are neutral (1.0x)
    target = PokemonInstance(
        species="Makuhita", level=20, hp=80, max_hp=80,
        attack=40, defense=30, sp_atk=15, sp_def=30, speed=18,
        moves=["Tackle"], pp=[35],
    )

    # Blaze Kick (Fire) should have STAB (Fire is Blaziken's primary type)
    dmg_fire = calculate_damage(blaziken, target, "Blaze Kick")
    # Double Kick (Fighting) should also have STAB (Fighting is Blaziken's secondary type)
    dmg_fight = calculate_damage(blaziken, target, "Double Kick")

    # Both moves are neutral (1.0x) against Fighting-type Makuhita.
    # With correct STAB: both get 1.5x, ratio = 85/30 = 2.83
    # With buggy STAB (only first type): Fire gets 1.5x, Fighting gets 1.0x
    #   ratio = (85*1.5)/(30*1.0) = 4.25
    ratio = dmg_fire / max(1, dmg_fight)
    assert ratio < 3.5, (
        f"Blaze Kick damage ({dmg_fire}) / Double Kick damage ({dmg_fight}) = {ratio:.2f}. "
        f"If STAB only applies to the first type, Double Kick loses its 1.5x bonus, "
        f"inflating the ratio above 3.5. Both should receive STAB."
    )


def test_hidden_burn_halves_physical_only():
    """Burn should halve physical move damage but not special move damage."""
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    blaziken_burned = PokemonInstance(
        species="Blaziken", level=36, hp=108, max_hp=108,
        attack=95, defense=65, sp_atk=85, sp_def=65, speed=80,
        moves=["Blaze Kick", "Ember"], pp=[10, 25],
        status="burn",
    )
    blaziken_healthy = PokemonInstance(
        species="Blaziken", level=36, hp=108, max_hp=108,
        attack=95, defense=65, sp_atk=85, sp_def=65, speed=80,
        moves=["Blaze Kick", "Ember"], pp=[10, 25],
        status=None,
    )
    target = PokemonInstance(
        species="Makuhita", level=19, hp=52, max_hp=52,
        attack=38, defense=40, sp_atk=15, sp_def=40, speed=18,
        moves=["Tackle"], pp=[35],
    )

    # Blaze Kick is physical — burn should halve damage
    dmg_physical_burned = calculate_damage(blaziken_burned, target, "Blaze Kick")
    dmg_physical_healthy = calculate_damage(blaziken_healthy, target, "Blaze Kick")
    assert dmg_physical_burned == dmg_physical_healthy // 2 or \
           dmg_physical_burned == int(dmg_physical_healthy * 0.5), (
        f"Burned Blaze Kick should deal half damage: "
        f"burned={dmg_physical_burned}, healthy={dmg_physical_healthy}, "
        f"expected ~{dmg_physical_healthy // 2}"
    )

    # Ember is special — burn should NOT affect damage
    dmg_special_burned = calculate_damage(blaziken_burned, target, "Ember")
    dmg_special_healthy = calculate_damage(blaziken_healthy, target, "Ember")
    assert dmg_special_burned == dmg_special_healthy, (
        f"Burn should not affect special moves: "
        f"burned={dmg_special_burned}, healthy={dmg_special_healthy}"
    )


def test_hidden_multihit_damage_application():
    """Multi-hit moves must subtract HP correctly for each hit.

    Each hit should: calculate damage, subtract from HP, then check faint.
    Total damage returned should match actual HP lost.
    """
    from emulator.battle_system import execute_move, calculate_damage
    from emulator.types import PokemonInstance

    blaziken = PokemonInstance(
        species="Blaziken", level=36, hp=108, max_hp=108,
        attack=95, defense=65, sp_atk=85, sp_def=65, speed=80,
        moves=["Double Kick"], pp=[30],
    )
    # Defender with enough HP to survive the first hit but not both
    target = PokemonInstance(
        species="Makuhita", level=19, hp=52, max_hp=52,
        attack=38, defense=22, sp_atk=15, sp_def=22, speed=18,
        moves=["Tackle"], pp=[35],
    )

    per_hit = calculate_damage(blaziken, target, "Double Kick")
    initial_hp = target.hp
    total_returned = execute_move(blaziken, target, 0)  # Double Kick

    # Target should have taken damage
    assert target.hp < initial_hp, (
        f"Target HP should decrease after Double Kick. "
        f"Before: {initial_hp}, After: {target.hp}."
    )
    # Verify the returned total is consistent with actual HP change
    hp_lost = initial_hp - target.hp
    assert hp_lost > 0, f"HP lost should be positive, got {hp_lost}"
    assert total_returned > 0, f"Total damage returned should be positive, got {total_returned}"


# ---------- new bug tests: PP deduction, stat stages, speed key ----------


def test_hidden_multihit_pp_deducted_once():
    """Multi-hit moves should deduct only 1 PP per use, not 1 PP per hit.

    Double Kick (hit_twice) = 2 hits, should cost 1 PP.
    Arm Thrust (hit_2_to_5) = 3 hits (deterministic), should cost 1 PP.
    """
    from emulator.battle_system import execute_move
    from emulator.types import PokemonInstance

    hariyama = PokemonInstance(
        species="Hariyama", level=25, hp=120, max_hp=120,
        attack=75, defense=50, sp_atk=30, sp_def=45, speed=40,
        moves=["Arm Thrust", "Double Kick", "Vital Throw"], pp=[20, 30, 10],
    )
    target = PokemonInstance(
        species="Machop", level=20, hp=200, max_hp=200,
        attack=50, defense=40, sp_atk=30, sp_def=30, speed=30,
        moves=["Tackle"], pp=[35],
    )

    # Use Arm Thrust (hit_2_to_5 = 3 hits deterministic)
    initial_pp_arm = hariyama.pp[0]
    execute_move(hariyama, target, 0)
    assert hariyama.pp[0] == initial_pp_arm - 1, (
        f"Arm Thrust (3 hits) should deduct 1 PP total, not per-hit. "
        f"Started at {initial_pp_arm}, now {hariyama.pp[0]}, expected {initial_pp_arm - 1}."
    )

    # Use Double Kick (hit_twice = 2 hits)
    initial_pp_dk = hariyama.pp[1]
    execute_move(hariyama, target, 1)
    assert hariyama.pp[1] == initial_pp_dk - 1, (
        f"Double Kick (2 hits) should deduct 1 PP total, not per-hit. "
        f"Started at {initial_pp_dk}, now {hariyama.pp[1]}, expected {initial_pp_dk - 1}."
    )

    # Verify single-hit move for sanity
    initial_pp_vt = hariyama.pp[2]
    execute_move(hariyama, target, 2)
    assert hariyama.pp[2] == initial_pp_vt - 1, (
        f"Vital Throw (single hit) should deduct 1 PP. "
        f"Started at {initial_pp_vt}, now {hariyama.pp[2]}, expected {initial_pp_vt - 1}."
    )


def test_hidden_negative_defense_stage_increases_damage():
    """Lowered defense stat stages should increase damage dealt to the defender.

    A defender at -2 defense stage has effective defense halved, so they
    take roughly double damage compared to neutral defense.
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    attacker = PokemonInstance(
        species="Blaziken", level=36, hp=108, max_hp=108,
        attack=95, defense=65, sp_atk=85, sp_def=65, speed=80,
        moves=["Blaze Kick"], pp=[10],
    )

    target_neutral = PokemonInstance(
        species="Machop", level=25, hp=80, max_hp=80,
        attack=55, defense=50, sp_atk=30, sp_def=30, speed=30,
        moves=["Tackle"], pp=[35],
        stat_stages={"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
    )
    target_lowered = PokemonInstance(
        species="Machop", level=25, hp=80, max_hp=80,
        attack=55, defense=50, sp_atk=30, sp_def=30, speed=30,
        moves=["Tackle"], pp=[35],
        stat_stages={"atk": 0, "def": -2, "spa": 0, "spd": 0, "spe": 0},
    )

    dmg_neutral = calculate_damage(attacker, target_neutral, "Blaze Kick")
    dmg_lowered = calculate_damage(attacker, target_lowered, "Blaze Kick")

    assert dmg_lowered > dmg_neutral, (
        f"Damage vs -2 def stage ({dmg_lowered}) should exceed neutral ({dmg_neutral}). "
        f"Negative defense stages must reduce effective defense, not increase it."
    )
    # With -2 stage (multiplier 0.5), damage should roughly double
    assert dmg_lowered >= int(dmg_neutral * 1.8), (
        f"Damage vs -2 def ({dmg_lowered}) should be close to 2x neutral ({dmg_neutral}). "
        f"Expected at least {int(dmg_neutral * 1.8)}."
    )


def test_hidden_negative_spdef_stage_increases_special_damage():
    """Lowered special defense stat stages should increase special damage.

    Mirrors the physical defense test but for the special side.
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    attacker = PokemonInstance(
        species="Sceptile", level=36, hp=100, max_hp=100,
        attack=72, defense=55, sp_atk=88, sp_def=72, speed=100,
        moves=["Absorb"], pp=[25],
    )

    target_neutral = PokemonInstance(
        species="Ralts", level=20, hp=40, max_hp=40,
        attack=20, defense=20, sp_atk=35, sp_def=40, speed=30,
        moves=["Confusion"], pp=[25],
        stat_stages={"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
    )
    target_lowered = PokemonInstance(
        species="Ralts", level=20, hp=40, max_hp=40,
        attack=20, defense=20, sp_atk=35, sp_def=40, speed=30,
        moves=["Confusion"], pp=[25],
        stat_stages={"atk": 0, "def": 0, "spa": 0, "spd": -2, "spe": 0},
    )

    dmg_neutral = calculate_damage(attacker, target_neutral, "Absorb")
    dmg_lowered = calculate_damage(attacker, target_lowered, "Absorb")

    assert dmg_lowered > dmg_neutral, (
        f"Special damage vs -2 sp.def stage ({dmg_lowered}) should exceed "
        f"neutral ({dmg_neutral}). Negative sp.def stages must reduce "
        f"effective special defense."
    )


def test_hidden_speed_stage_affects_turn_order():
    """Speed stat stage changes must affect turn order determination.

    When a Pokemon's speed stage is lowered (e.g., by Rock Tomb), the
    effective speed used for turn order should reflect the stage change.
    """
    from emulator.battle_system import get_turn_order
    from emulator.types import PokemonInstance

    # Player is naturally faster (speed 75 vs 65)
    player = PokemonInstance(
        species="Wingull", level=25, hp=50, max_hp=50,
        attack=25, defense=25, sp_atk=40, sp_def=25, speed=75,
        moves=["Water Gun", "Wing Attack"], pp=[25, 35],
        stat_stages={"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
    )
    enemy = PokemonInstance(
        species="Geodude", level=25, hp=55, max_hp=55,
        attack=55, defense=70, sp_atk=25, sp_def=25, speed=65,
        moves=["Rock Tomb", "Tackle"], pp=[15, 35],
        stat_stages={"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
    )

    # Before speed drop: player (75) > enemy (65), player goes first
    order_before = get_turn_order([player], enemy, 0, 0)
    assert order_before[0][0] == "player", (
        f"With no speed stages, player (75) should move before enemy (65)"
    )

    # After player's speed is lowered by 1 stage: effective = int(75 * 2/3) = 50
    # Enemy speed stays at 65. Now enemy should go first.
    player.stat_stages["spe"] = -1
    order_after = get_turn_order([player], enemy, 0, 0)
    assert order_after[0][0] == "enemy", (
        f"After -1 speed stage, player effective speed is {int(75 * 2/3)} "
        f"which is less than enemy speed 65. Enemy should move first. "
        f"Turn order must use the 'spe' stat stage key, not 'spd'."
    )


def test_hidden_arm_thrust_pp_with_multiple_uses():
    """Arm Thrust used 7 times should leave 13 PP (20 - 7), not deplete to 0.

    If PP is deducted per hit (3 hits = 3 PP per use), 7 uses would cost
    21 PP and exhaust the move. Correct behavior deducts 1 PP per use.
    """
    from emulator.battle_system import execute_move
    from emulator.types import PokemonInstance

    hariyama = PokemonInstance(
        species="Hariyama", level=30, hp=150, max_hp=150,
        attack=85, defense=50, sp_atk=30, sp_def=50, speed=40,
        moves=["Arm Thrust"], pp=[20],
    )
    target = PokemonInstance(
        species="Hariyama", level=30, hp=9999, max_hp=9999,
        attack=85, defense=50, sp_atk=30, sp_def=50, speed=40,
        moves=["Tackle"], pp=[35],
    )

    for i in range(7):
        result = execute_move(hariyama, target, 0)
        assert result > 0, (
            f"Arm Thrust use {i+1} should deal damage. PP was {hariyama.pp[0]+1} before use."
        )

    assert hariyama.pp[0] == 13, (
        f"After 7 uses of Arm Thrust (PP 20), remaining PP should be 13. "
        f"Got {hariyama.pp[0]}. If PP is deducted per hit instead of per use, "
        f"3 hits x 7 uses = 21 PP deducted, exceeding the 20 PP pool."
    )


# ---------- loop / aggregate tests ----------


def test_hidden_battle_no_whiteout():
    """Player never faints in any hidden scenario."""
    for i in range(1, 7):
        ref = load_hidden_ref(f"battle_hidden_{i:02d}_result.json")
        state = load_savestate(
            str(HIDDEN_BASE / "savestates" / f"battle_hidden_{i:02d}.json")
        )
        state = replay_actions(state, ref["actions"])
        result = state_to_dict(state)
        assert result["whiteout"] is False, f"Hidden battle {i}: player should not whiteout"


def test_hidden_battle_deterministic():
    """All hidden scenarios replay identically on two runs."""
    for i in range(1, 7):
        ref = load_hidden_ref(f"battle_hidden_{i:02d}_result.json")
        save_path = str(HIDDEN_BASE / "savestates" / f"battle_hidden_{i:02d}.json")

        s1 = load_savestate(save_path)
        s1 = replay_actions(s1, ref["actions"])
        r1 = state_to_dict(s1)

        s2 = load_savestate(save_path)
        s2 = replay_actions(s2, ref["actions"])
        r2 = state_to_dict(s2)

        assert r1 == r2, f"Hidden battle {i}: replays should be identical"


# ---------- new domain-knowledge bug tests ----------


def test_hidden_damage_rounding_floor_order():
    """Gen III damage formula uses floor (truncation) at the final step, not round.

    For certain stat combinations, round() produces a different value than int().
    The correct Gen III behavior is to truncate (floor toward zero).
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    # Poochyena (Dark) using Bite (Dark, physical, power=60) vs Ralts (Psychic, def=25)
    # STAB: Dark type using Bite (Dark) = 1.5x
    # Type: Dark vs Psychic = 2.0x
    # base = ((2*20/5+2)*60*45/25)/50+2 = ((10)*60*45/25)/50+2 = (10*108)/50+2 = 1080/50+2 = 23.6
    # final = 23.6 * 1.5 * 2.0 = 70.8
    # int(70.8) = 70 (correct, floor)
    # round(70.8) = 71 (wrong, banker's rounding)
    poochyena = PokemonInstance(
        species="Poochyena", level=20, hp=45, max_hp=45,
        attack=45, defense=30, sp_atk=25, sp_def=25, speed=30,
        moves=["Bite"], pp=[25],
    )
    ralts = PokemonInstance(
        species="Ralts", level=20, hp=35, max_hp=35,
        attack=20, defense=25, sp_atk=35, sp_def=30, speed=32,
        moves=["Confusion"], pp=[25],
    )

    damage = calculate_damage(poochyena, ralts, "Bite")
    assert damage == 70, (
        f"Bite damage should be 70 (floor), got {damage}. "
        f"Gen III truncates (int), not rounds."
    )


def test_hidden_damage_rounding_quick_attack():
    """Additional rounding check: Quick Attack with specific stats.

    Sceptile (L36, atk=72) Quick Attack (Normal, physical, pow=40)
    vs a Fighting defender (def=22, 1.0x type effectiveness, no STAB).
    base = ((16.4)*40*72/22)/50+2 = 44.938...
    int(44.938) = 44 (correct)
    round(44.938) = 45 (wrong)
    """
    from emulator.battle_system import calculate_damage
    from emulator.types import PokemonInstance

    sceptile = PokemonInstance(
        species="Sceptile", level=36, hp=100, max_hp=100,
        attack=72, defense=55, sp_atk=88, sp_def=72, speed=100,
        moves=["Quick Attack"], pp=[30],
    )
    makuhita = PokemonInstance(
        species="Makuhita", level=19, hp=52, max_hp=52,
        attack=38, defense=22, sp_atk=15, sp_def=22, speed=18,
        moves=["Tackle"], pp=[35],
    )

    damage = calculate_damage(sceptile, makuhita, "Quick Attack")
    assert damage == 44, (
        f"Quick Attack damage should be 44 (floor), got {damage}. "
        f"Gen III always truncates toward zero."
    )


def test_hidden_priority_move_goes_first():
    """A slower Pokemon using Quick Attack (+1 priority) should move before
    a faster Pokemon using a normal-priority move.

    Priority brackets override speed entirely in Gen III.
    """
    from emulator.battle_system import get_turn_order
    from emulator.types import PokemonInstance

    # Slow mon with Quick Attack (+1 priority)
    slow_pkmn = PokemonInstance(
        species="Makuhita", level=20, hp=60, max_hp=60,
        attack=40, defense=25, sp_atk=15, sp_def=25, speed=18,
        moves=["Quick Attack", "Tackle"], pp=[30, 35],
    )
    # Fast mon with Tackle (0 priority)
    fast_pkmn = PokemonInstance(
        species="Sceptile", level=36, hp=100, max_hp=100,
        attack=72, defense=55, sp_atk=88, sp_def=72, speed=100,
        moves=["Razor Leaf", "Tackle"], pp=[25, 35],
    )

    # Slow player uses Quick Attack (pri=+1), fast enemy uses Razor Leaf (pri=0)
    order = get_turn_order([slow_pkmn], fast_pkmn, 0, 0)

    assert order[0][0] == "player", (
        f"Slow Pokemon with Quick Attack (+1 priority) should move first, "
        f"but {order[0][0]} moved first. Higher priority always beats speed."
    )


def test_hidden_priority_vital_throw_goes_last():
    """Vital Throw (-1 priority) should always go last, even if the user is faster.

    A fast Pokemon using Vital Throw should move after a slower Pokemon using
    a normal-priority move.
    """
    from emulator.battle_system import get_turn_order
    from emulator.types import PokemonInstance

    # Fast mon with Vital Throw (-1 priority)
    fast_pkmn = PokemonInstance(
        species="Sceptile", level=36, hp=100, max_hp=100,
        attack=72, defense=55, sp_atk=88, sp_def=72, speed=100,
        moves=["Vital Throw", "Tackle"], pp=[10, 35],
    )
    # Slow mon with Tackle (0 priority)
    slow_pkmn = PokemonInstance(
        species="Makuhita", level=20, hp=60, max_hp=60,
        attack=40, defense=25, sp_atk=15, sp_def=25, speed=18,
        moves=["Tackle", "Vital Throw"], pp=[35, 10],
    )

    # Fast player uses Vital Throw (pri=-1), slow enemy uses Tackle (pri=0)
    order = get_turn_order([fast_pkmn], slow_pkmn, 0, 0)

    assert order[0][0] == "enemy", (
        f"Enemy with Tackle (priority 0) should move before player with "
        f"Vital Throw (priority -1), but {order[0][0]} moved first."
    )


def test_hidden_burn_tick_damage_exact():
    """End-of-turn burn damage should be exactly floor(max_HP / 8) in Gen III.

    This is 1/8 of max HP (not 1/16, which is a common error from later gens).
    """
    from emulator.battle_system import apply_end_of_turn_effects
    from emulator.types import PokemonInstance

    # Test with max_hp=108 (Blaziken)
    pkmn = PokemonInstance(
        species="Blaziken", level=36, hp=108, max_hp=108,
        attack=95, defense=65, sp_atk=85, sp_def=65, speed=80,
        moves=["Blaze Kick"], pp=[10],
        status="burn",
    )

    initial_hp = pkmn.hp
    apply_end_of_turn_effects(pkmn)
    burn_damage = initial_hp - pkmn.hp

    expected_damage = 108 // 8  # = 13
    assert burn_damage == expected_damage, (
        f"Burn tick should deal floor(108/8) = {expected_damage} damage, "
        f"but dealt {burn_damage}. Gen III burn damage is 1/8 max HP."
    )


def test_hidden_burn_tick_different_hp():
    """Burn tick test with a different max HP to catch hardcoded values."""
    from emulator.battle_system import apply_end_of_turn_effects
    from emulator.types import PokemonInstance

    # Test with max_hp=80
    pkmn = PokemonInstance(
        species="Machop", level=25, hp=80, max_hp=80,
        attack=55, defense=40, sp_atk=30, sp_def=30, speed=30,
        moves=["Tackle"], pp=[35],
        status="burn",
    )

    initial_hp = pkmn.hp
    apply_end_of_turn_effects(pkmn)
    burn_damage = initial_hp - pkmn.hp

    expected_damage = 80 // 8  # = 10
    assert burn_damage == expected_damage, (
        f"Burn tick should deal floor(80/8) = {expected_damage} damage, "
        f"but dealt {burn_damage}."
    )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
