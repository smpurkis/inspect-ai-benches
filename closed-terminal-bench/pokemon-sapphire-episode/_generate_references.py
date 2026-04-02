#!/usr/bin/env python3
"""Generate all savestate and reference files for pokemon-sapphire-episode.

Run from the pokemon-sapphire-episode directory.
"""

import json
import copy
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "steps/step_1/files")

from emulator.constants import MOVE_DATA, SPECIES_DATA, EFFECTIVENESS, get_stat_multiplier


# ── Helpers ──────────────────────────────────────────────────────────────

def ascii_to_grid(lines, npcs=None, items=None, exits=None, trainers=None, grass=None):
    npcs = npcs or {}; items = items or {}; exits = exits or set()
    trainers = trainers or {}; grass = grass or set()
    grid = []
    for y, line in enumerate(lines):
        row = []
        for x, ch in enumerate(line):
            tile = {"walkable": ch == "."}
            pos = (x, y)
            if pos in npcs:
                tile["has_npc"] = True; tile["npc_name"] = npcs[pos]; tile["walkable"] = False
            if pos in items:
                tile["has_item"] = True; tile["item_name"] = items[pos]; tile["walkable"] = True
            if pos in exits:
                tile["is_exit"] = True; tile["walkable"] = True
            if pos in grass:
                tile["is_grass"] = True
            if pos in trainers:
                tile["trainer"] = trainers[pos]; tile["walkable"] = False
            row.append(tile)
        grid.append(row)
    return grid


def pkmn(species, level, hp, max_hp, atk, dfn, spa, spd, spe, moves, pp, status=None):
    return {
        "species": species, "level": level, "hp": hp, "max_hp": max_hp,
        "attack": atk, "defense": dfn, "sp_atk": spa, "sp_def": spd, "speed": spe,
        "moves": moves, "pp": list(pp), "status": status,
        "stat_stages": {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
    }


def correct_damage(attacker, defender, move_name):
    move = MOVE_DATA[move_name]
    if move["category"] == "status":
        return 0
    power = move["power"]
    level = attacker["level"]
    def_types = SPECIES_DATA.get(defender["species"], {}).get("types", ["Normal"])
    tm = 1.0
    for dt in def_types:
        tm *= EFFECTIVENESS.get(move["type"], {}).get(dt, 1.0)
    if tm <= 0:
        return 0
    if move["category"] == "physical":
        a = int(attacker["attack"] * get_stat_multiplier(attacker["stat_stages"].get("atk", 0)))
        d = max(1, int(defender["defense"] * get_stat_multiplier(defender["stat_stages"].get("def", 0))))
    else:
        a = int(attacker["sp_atk"] * get_stat_multiplier(attacker["stat_stages"].get("spa", 0)))
        d = max(1, int(defender["sp_def"] * get_stat_multiplier(defender["stat_stages"].get("spd", 0))))
    atk_types = SPECIES_DATA.get(attacker["species"], {}).get("types", [])
    stab = 1.5 if move["type"] in atk_types else 1.0
    base = ((2 * level / 5 + 2) * power * a / d) / 50 + 2
    return max(1, int(base * stab * tm))


def enemy_ai(enemy):
    best_idx, best_pow = 0, -1
    for i, mn in enumerate(enemy["moves"]):
        if enemy["pp"][i] <= 0: continue
        p = MOVE_DATA.get(mn, {}).get("power", 0)
        if p > best_pow: best_pow = p; best_idx = i
    return best_idx


def simulate_battle_with_engine(player, enemies):
    """Simulate battle exactly as the CORRECT engine does.

    Matches _process_battle_moves behavior:
    - Action A on BATTLE_MAIN -> BATTLE_MOVES
    - Action A on BATTLE_MOVES -> execute turn
    - After enemy KO (not all fainted): screen stays BATTLE_MOVES, next active
    - After all fainted: screen -> DIALOGUE

    Returns (actions, final_player_dict)
    """
    player = copy.deepcopy(player)
    enemies = [copy.deepcopy(e) for e in enemies]
    actions = []
    eidx = 0

    # First A: BATTLE_MAIN -> BATTLE_MOVES
    actions.append("A")

    while eidx < len(enemies):
        enemy = enemies[eidx]
        if enemy["hp"] <= 0:
            eidx += 1
            continue

        # A on BATTLE_MOVES: execute move 0
        actions.append("A")

        # Determine turn order
        p_move_name = player["moves"][0]
        e_mi = enemy_ai(enemy)
        e_move_name = enemy["moves"][e_mi]
        p_pri = MOVE_DATA[p_move_name].get("priority", 0)
        e_pri = MOVE_DATA[e_move_name].get("priority", 0)
        p_spd = int(player["speed"] * get_stat_multiplier(player["stat_stages"].get("spe", 0)))
        e_spd = int(enemy["speed"] * get_stat_multiplier(enemy["stat_stages"].get("spe", 0)))

        if p_pri > e_pri or (p_pri == e_pri and p_spd >= e_spd):
            order = [("p", 0), ("e", e_mi)]
        else:
            order = [("e", e_mi), ("p", 0)]

        for side, mi in order:
            atk = player if side == "p" else enemy
            dfn = enemy if side == "p" else player
            if atk["hp"] <= 0:
                continue
            mn = atk["moves"][mi]
            move = MOVE_DATA[mn]
            if atk["pp"][mi] > 0:
                atk["pp"][mi] -= 1
            hits = 1
            if move.get("effect") == "hit_twice": hits = 2
            elif move.get("effect") == "hit_2_to_5": hits = 3
            for _ in range(hits):
                dmg = correct_damage(atk, dfn, mn)
                dfn["hp"] -= dmg
                if dfn["hp"] <= 0:
                    dfn["hp"] = 0
                    break
            eff = move.get("effect")
            if eff == "boost_atk_def":
                atk["stat_stages"]["atk"] = min(6, atk["stat_stages"].get("atk", 0) + 1)
                atk["stat_stages"]["def"] = min(6, atk["stat_stages"].get("def", 0) + 1)
            elif eff == "lower_speed":
                dfn["stat_stages"]["spe"] = max(-6, dfn["stat_stages"].get("spe", 0) - 1)
            if dfn["hp"] <= 0:
                break

        # EOT
        for p in [player, enemy]:
            if p["hp"] > 0 and p.get("status") == "poison":
                p["hp"] = max(0, p["hp"] - max(1, p["max_hp"] // 8))
            elif p["hp"] > 0 and p.get("status") == "burn":
                p["hp"] = max(0, p["hp"] - max(1, p["max_hp"] // 16))

        if enemy["hp"] <= 0:
            eidx += 1
            if eidx < len(enemies):
                # More enemies: screen stays BATTLE_MOVES, no extra action needed
                pass
            # If all fainted: screen -> DIALOGUE (we stop adding actions)

        elif player["hp"] <= 0:
            break  # player fainted

        else:
            # Neither fainted: screen -> BATTLE_MAIN, need another A to get to BATTLE_MOVES
            actions.append("A")

    return actions, player


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path}")


# ── Pokemon templates ────────────────────────────────────────────────────

BLAZIKEN = pkmn("Blaziken", 36, 108, 108, 95, 65, 85, 65, 80,
    ["Blaze Kick", "Double Kick", "Peck", "Bulk Up"], [10, 30, 35, 20])

SCEPTILE = pkmn("Sceptile", 36, 100, 100, 72, 55, 88, 72, 100,
    ["Razor Leaf", "Quick Attack", "Absorb", "Bulk Up"], [25, 30, 25, 20])

SWAMPERT = pkmn("Swampert", 36, 120, 120, 92, 78, 72, 78, 55,
    ["Water Gun", "Mud Shot", "Tackle", "Rock Tomb"], [25, 15, 35, 15])

BRAWLY_MACHOP = pkmn("Machop", 17, 44, 44, 42, 32, 22, 22, 22,
    ["Karate Chop", "Bulk Up", "Sand Attack", "Tackle"], [25, 20, 15, 35])

BRAWLY_MAKUHITA = pkmn("Makuhita", 19, 52, 52, 38, 22, 15, 22, 18,
    ["Arm Thrust", "Vital Throw", "Sand Attack", "Bulk Up"], [20, 10, 15, 20])

# For hidden_01: dual-type enemy to catch bug 6
ARON = pkmn("Aron", 15, 50, 50, 35, 45, 22, 22, 16,
    ["Rock Tomb", "Tackle", "Poison Sting", "Sand Attack"], [15, 35, 35, 15])

GYM_MEDITITE = pkmn("Meditite", 16, 35, 35, 28, 34, 28, 34, 36,
    ["Confusion", "Bulk Up", "Tackle", "Focus Energy"], [25, 20, 35, 30])

GYM_MACHOP = pkmn("Machop", 16, 43, 43, 41, 31, 22, 22, 22,
    ["Karate Chop", "Bulk Up", "Tackle", "Focus Energy"], [25, 20, 35, 30])


# ── STEP 1 ──────────────────────────────────────────────────────────────

def gen_step1():
    print("Step 1:")

    # Visible: Blaziken vs Brawly (Machop + Makuhita)
    vis_save = {
        "screen": "battle_main",
        "player_party": [copy.deepcopy(BLAZIKEN)],
        "enemy_trainer": {
            "name": "Brawly", "active_index": 0, "defeated": False,
            "party": [copy.deepcopy(BRAWLY_MACHOP), copy.deepcopy(BRAWLY_MAKUHITA)],
        },
        "wild_pokemon": None,
        "player_position": [3, 5], "player_facing": "UP",
        "map_grid": [], "map_name": "Dewford Gym",
        "battle_active": True, "battle_won": None, "cursor_position": 0,
        "flags": {"battle_context": "Gym Leader"},
        "inventory": {}, "badges": 0,
        "dialogue_text": "Gym Leader Brawly wants to battle!",
    }
    write_json("steps/step_1/files/savestates/battle_visible.json", vis_save)

    actions, player = simulate_battle_with_engine(
        copy.deepcopy(BLAZIKEN),
        [copy.deepcopy(BRAWLY_MACHOP), copy.deepcopy(BRAWLY_MAKUHITA)],
    )
    write_json("steps/step_1/files/reference/battle_visible_result.json", {
        "battle_won": True, "whiteout": False,
        "player_hp": player["hp"], "player_max_hp": player["max_hp"],
        "player_pp": player["pp"],
        "action_count": len(actions), "actions": actions,
        "trainer_defeated": True, "badges": 1,
    })
    print(f"  visible: {len(actions)} actions, HP={player['hp']}/{player['max_hp']}")

    # Hidden 01: Sceptile vs Aron (Steel/Rock dual type — catches bug 6)
    h1_save = {
        "screen": "battle_main",
        "player_party": [copy.deepcopy(SCEPTILE)],
        "enemy_trainer": {
            "name": "Hiker", "active_index": 0, "defeated": False,
            "party": [copy.deepcopy(ARON)],
        },
        "wild_pokemon": None,
        "player_position": [3, 5], "player_facing": "UP",
        "map_grid": [], "map_name": "Route 106",
        "battle_active": True, "battle_won": None, "cursor_position": 0,
        "flags": {}, "inventory": {}, "badges": 1,
        "dialogue_text": "Hiker wants to battle!",
    }
    write_json("steps/step_1/hidden/savestates/battle_hidden_01.json", h1_save)
    h1_act, h1_p = simulate_battle_with_engine(
        copy.deepcopy(SCEPTILE), [copy.deepcopy(ARON)])
    write_json("steps/step_1/hidden/reference/battle_hidden_01_result.json", {
        "battle_won": True, "whiteout": False,
        "player_hp": h1_p["hp"], "player_max_hp": h1_p["max_hp"],
        "player_pp": h1_p["pp"],
        "action_count": len(h1_act), "actions": h1_act, "trainer_defeated": True,
    })
    print(f"  hidden_01: {len(h1_act)} actions, HP={h1_p['hp']}/{h1_p['max_hp']} (Sceptile vs Aron)")

    # Hidden 02: Low HP Blaziken vs Makuhita
    low_hp = copy.deepcopy(BLAZIKEN); low_hp["hp"] = 25
    h2_save = copy.deepcopy(vis_save)
    h2_save["player_party"] = [low_hp]
    h2_save["enemy_trainer"] = {
        "name": "Brawly", "active_index": 0, "defeated": False,
        "party": [copy.deepcopy(BRAWLY_MAKUHITA)],
    }
    h2_save["flags"] = {}
    h2_save["dialogue_text"] = "Brawly wants to battle!"
    write_json("steps/step_1/hidden/savestates/battle_hidden_02.json", h2_save)
    h2_act, h2_p = simulate_battle_with_engine(
        copy.deepcopy(low_hp), [copy.deepcopy(BRAWLY_MAKUHITA)])
    write_json("steps/step_1/hidden/reference/battle_hidden_02_result.json", {
        "battle_won": True, "whiteout": False,
        "player_hp": h2_p["hp"], "player_max_hp": h2_p["max_hp"],
        "player_pp": h2_p["pp"],
        "action_count": len(h2_act), "actions": h2_act, "trainer_defeated": True,
    })
    print(f"  hidden_02: {len(h2_act)} actions, HP={h2_p['hp']}/{h2_p['max_hp']}")

    # Hidden 03: Blaziken vs poisoned Makuhita
    poison_maku = copy.deepcopy(BRAWLY_MAKUHITA); poison_maku["status"] = "poison"
    h3_save = copy.deepcopy(vis_save)
    h3_save["enemy_trainer"] = {
        "name": "Brawly", "active_index": 0, "defeated": False,
        "party": [poison_maku],
    }
    h3_save["flags"] = {}
    h3_save["dialogue_text"] = "Brawly wants to battle!"
    write_json("steps/step_1/hidden/savestates/battle_hidden_03.json", h3_save)
    h3_act, h3_p = simulate_battle_with_engine(
        copy.deepcopy(BLAZIKEN), [copy.deepcopy(poison_maku)])
    write_json("steps/step_1/hidden/reference/battle_hidden_03_result.json", {
        "battle_won": True, "whiteout": False,
        "player_hp": h3_p["hp"], "player_max_hp": h3_p["max_hp"],
        "player_pp": h3_p["pp"],
        "action_count": len(h3_act), "actions": h3_act, "trainer_defeated": True,
    })
    print(f"  hidden_03: {len(h3_act)} actions, HP={h3_p['hp']}/{h3_p['max_hp']}")


# ── STEP 2 ──────────────────────────────────────────────────────────────

def gen_step2():
    print("Step 2:")

    # Visible: Route 106 (10x8)
    # ##########
    # #.......E#   Exit at (8,1)
    # #...N....#   NPC "Sailor" at (4,2)
    # #.####...#   walls at x=2..5
    # #........#
    # #..!.....#   item "Potion" at (3,5)
    # #........#   player at (1,6)
    # ##########
    vis_grid = ascii_to_grid([
        "##########",
        "#........#",
        "#........#",
        "#.####...#",
        "#........#",
        "#........#",
        "#........#",
        "##########",
    ], npcs={(4, 2): "Sailor"}, items={(3, 5): "Potion"}, exits={(8, 1)})

    vis_save = {
        "screen": "overworld",
        "player_party": [copy.deepcopy(BLAZIKEN)],
        "enemy_trainer": None, "wild_pokemon": None,
        "player_position": [1, 6], "player_facing": "UP",
        "map_grid": vis_grid, "map_name": "Route 106",
        "battle_active": False, "battle_won": None, "cursor_position": 0,
        "flags": {}, "inventory": {}, "badges": 1, "dialogue_text": "",
    }
    write_json("steps/step_2/files/savestates/route_visible.json", vis_save)

    # Verified path: UP*4 to (1,2), RIGHT*3 blocked at NPC,
    # A talk, A dismiss, LEFT*2 to (1,2), DOWN*3 to (1,5),
    # RIGHT*2 to (3,5) item+dialogue, A dismiss,
    # RIGHT*5 to (8,5), UP*4 to (8,1) exit
    vis_actions = (
        ["UP"] * 4 + ["RIGHT"] * 3 +
        ["A", "A"] +
        ["LEFT"] * 2 + ["DOWN"] * 3 + ["RIGHT"] * 2 +
        ["A"] +
        ["RIGHT"] * 5 + ["UP"] * 4
    )
    write_json("steps/step_2/files/reference/route_visible_result.json", {
        "reached_exit": True, "talked_to_Sailor": True, "picked_up_Potion": True,
        "player_position": [8, 1], "action_count": len(vis_actions),
        "actions": vis_actions, "whiteout": False,
    })
    print(f"  visible: {len(vis_actions)} actions")

    # Hidden 01: open map, NPC "Fisherman" at (7,2), exit at (6,5)
    h1_grid = ascii_to_grid([
        "##########", "#........#", "#........#", "#........#",
        "#........#", "#........#", "#........#", "##########",
    ], npcs={(7, 2): "Fisherman"}, exits={(6, 5)})
    h1_save = {
        "screen": "overworld",
        "player_party": [copy.deepcopy(BLAZIKEN)],
        "enemy_trainer": None, "wild_pokemon": None,
        "player_position": [1, 1], "player_facing": "RIGHT",
        "map_grid": h1_grid, "map_name": "Route 107",
        "battle_active": False, "battle_won": None, "cursor_position": 0,
        "flags": {}, "inventory": {}, "badges": 1, "dialogue_text": "",
    }
    write_json("steps/step_2/hidden/savestates/route_hidden_01.json", h1_save)
    # Path: RIGHT*5 to (6,1), DOWN to (6,2), RIGHT blocked by NPC,
    # A talk, A dismiss, DOWN*3 to (6,5) exit
    h1_actions = ["RIGHT"]*5 + ["DOWN"] + ["RIGHT"] + ["A","A"] + ["DOWN"]*3
    write_json("steps/step_2/hidden/reference/route_hidden_01_result.json", {
        "reached_exit": True, "talked_to_Fisherman": True,
        "player_position": [6, 5], "action_count": len(h1_actions),
        "actions": h1_actions, "whiteout": False,
    })
    print(f"  hidden_01: {len(h1_actions)} actions")

    # Hidden 02: NPC "Hiker" at (3,2), exit at (8,1)
    h2_grid = ascii_to_grid([
        "##########", "#........#", "#........#", "#...#....#",
        "#........#", "#........#", "#........#", "##########",
    ], npcs={(3, 2): "Hiker"}, exits={(8, 1)})
    h2_save = {
        "screen": "overworld",
        "player_party": [copy.deepcopy(BLAZIKEN)],
        "enemy_trainer": None, "wild_pokemon": None,
        "player_position": [1, 6], "player_facing": "UP",
        "map_grid": h2_grid, "map_name": "Route 108",
        "battle_active": False, "battle_won": None, "cursor_position": 0,
        "flags": {}, "inventory": {}, "badges": 1, "dialogue_text": "",
    }
    write_json("steps/step_2/hidden/savestates/route_hidden_02.json", h2_save)
    # Path: UP*4 to (1,2), RIGHT to (2,2), RIGHT blocked NPC at (3,2),
    # A talk, A dismiss, UP to (2,1), RIGHT*6 to (8,1) exit
    h2_actions = ["UP"]*4 + ["RIGHT"] + ["RIGHT"] + ["A","A"] + ["UP"] + ["RIGHT"]*6
    write_json("steps/step_2/hidden/reference/route_hidden_02_result.json", {
        "reached_exit": True, "talked_to_Hiker": True,
        "player_position": [8, 1], "action_count": len(h2_actions),
        "actions": h2_actions, "whiteout": False,
    })
    print(f"  hidden_02: {len(h2_actions)} actions")

    # Hidden 03: NPC "Ranger" at (2,2), item "Super Potion" at (7,5), exit at (8,1)
    h3_grid = ascii_to_grid([
        "##########", "#........#", "#........#", "#........#",
        "#........#", "#........#", "#........#", "##########",
    ], npcs={(2, 2): "Ranger"}, items={(7, 5): "Super Potion"}, exits={(8, 1)})
    h3_save = {
        "screen": "overworld",
        "player_party": [copy.deepcopy(BLAZIKEN)],
        "enemy_trainer": None, "wild_pokemon": None,
        "player_position": [1, 6], "player_facing": "UP",
        "map_grid": h3_grid, "map_name": "Route 109",
        "battle_active": False, "battle_won": None, "cursor_position": 0,
        "flags": {}, "inventory": {}, "badges": 1, "dialogue_text": "",
    }
    write_json("steps/step_2/hidden/savestates/route_hidden_03.json", h3_save)
    # Path: UP*4 to (1,2), RIGHT blocked NPC at (2,2),
    # A talk, A dismiss, DOWN*3 to (1,5), RIGHT*6 to (7,5) item+dialogue,
    # A dismiss, RIGHT to (8,5), UP*4 to (8,1) exit
    h3_actions = (
        ["UP"]*4 + ["RIGHT"] + ["A","A"] +
        ["DOWN"]*3 + ["RIGHT"]*6 + ["A"] +
        ["RIGHT"] + ["UP"]*4
    )
    write_json("steps/step_2/hidden/reference/route_hidden_03_result.json", {
        "reached_exit": True, "talked_to_Ranger": True,
        "picked_up_Super Potion": True,
        "player_position": [8, 1], "action_count": len(h3_actions),
        "actions": h3_actions, "whiteout": False,
    })
    print(f"  hidden_03: {len(h3_actions)} actions")


# ── STEP 3 ──────────────────────────────────────────────────────────────

def gen_step3():
    print("Step 3:")

    gym_map = [
        "############", "#..........#", "#..........#", "#..........#",
        "#.####.....#", "#..........#", "#..........#", "#..........#",
        "#..........#", "############",
    ]
    leader_data = {
        "name": "Leader Brawly", "active_index": 0, "defeated": False,
        "party": [copy.deepcopy(BRAWLY_MACHOP), copy.deepcopy(BRAWLY_MAKUHITA)],
    }
    t1_data = {
        "name": "Battle Girl Laura", "active_index": 0, "defeated": False,
        "party": [copy.deepcopy(GYM_MEDITITE)],
    }
    t2_data = {
        "name": "Black Belt Takao", "active_index": 0, "defeated": False,
        "party": [copy.deepcopy(GYM_MACHOP)],
    }
    gym_grid = ascii_to_grid(gym_map, trainers={
        (5, 2): leader_data, (2, 5): t1_data, (8, 6): t2_data,
    })

    vis_save = {
        "screen": "overworld",
        "player_party": [copy.deepcopy(BLAZIKEN)],
        "enemy_trainer": None, "wild_pokemon": None,
        "player_position": [6, 8], "player_facing": "UP",
        "map_grid": gym_grid, "map_name": "Dewford Gym",
        "battle_active": False, "battle_won": None, "cursor_position": 0,
        "flags": {"battle_context": "Gym Leader"},
        "inventory": {"Potion": 3}, "badges": 0, "dialogue_text": "",
    }
    write_json("steps/step_3/files/savestates/gym_visible.json", vis_save)
    write_json("steps/step_3/files/reference/gym_visible_result.json", {
        "gym_leader_defeated": True, "badge_obtained": True,
        "badges": 1, "whiteout": False, "all_trainers_defeated": True,
        "max_action_count": 600,
    })
    print("  visible: gym reference written")

    # Hidden 01: Swampert party
    h1_save = copy.deepcopy(vis_save)
    h1_save["player_party"] = [copy.deepcopy(SWAMPERT)]
    h1_save["map_grid"] = ascii_to_grid(gym_map, trainers={
        (5, 2): copy.deepcopy(leader_data),
        (2, 5): copy.deepcopy(t1_data),
        (8, 6): copy.deepcopy(t2_data),
    })
    write_json("steps/step_3/hidden/savestates/gym_hidden_01.json", h1_save)
    write_json("steps/step_3/hidden/reference/gym_hidden_01_result.json", {
        "gym_leader_defeated": True, "badge_obtained": True,
        "badges": 1, "whiteout": False, "all_trainers_defeated": True,
        "max_action_count": 600,
    })

    # Hidden 02: Reduced PP
    h2_blaz = copy.deepcopy(BLAZIKEN); h2_blaz["pp"] = [3, 8, 10, 5]
    h2_save = copy.deepcopy(vis_save)
    h2_save["player_party"] = [h2_blaz]
    h2_save["inventory"] = {"Potion": 5}
    h2_save["map_grid"] = ascii_to_grid(gym_map, trainers={
        (5, 2): copy.deepcopy(leader_data),
        (2, 5): copy.deepcopy(t1_data),
        (8, 6): copy.deepcopy(t2_data),
    })
    write_json("steps/step_3/hidden/savestates/gym_hidden_02.json", h2_save)
    write_json("steps/step_3/hidden/reference/gym_hidden_02_result.json", {
        "gym_leader_defeated": True, "badge_obtained": True,
        "badges": 1, "whiteout": False, "all_trainers_defeated": True,
        "max_action_count": 600,
    })
    print("  hidden: gym references written")


if __name__ == "__main__":
    gen_step1()
    gen_step2()
    gen_step3()
    print("\nAll files generated!")
