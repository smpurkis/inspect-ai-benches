"""Main game engine for Pokemon Sapphire mock emulator.

Loads savestate JSON, processes button presses, manages screen transitions.

KNOWN ISSUES: This module has bugs that need to be fixed.
"""

import json
import copy
from typing import Optional

from .types import (
    GameState, GameScreen, PokemonInstance, Trainer,
    MapTile, Direction, Button,
)
from .constants import MOVE_DATA, SPECIES_DATA
from .battle_system import (
    execute_move, check_faint, apply_end_of_turn_effects,
    get_turn_order, select_enemy_move, apply_move_effect,
)


def load_savestate(path: str) -> GameState:
    """Load a savestate from a JSON file and return a GameState."""
    with open(path, "r") as f:
        data = json.load(f)

    player_party = []
    for pdata in data.get("player_party", []):
        pkmn = PokemonInstance(
            species=pdata["species"],
            level=pdata["level"],
            hp=pdata["hp"],
            max_hp=pdata["max_hp"],
            attack=pdata["attack"],
            defense=pdata["defense"],
            sp_atk=pdata["sp_atk"],
            sp_def=pdata["sp_def"],
            speed=pdata["speed"],
            moves=pdata["moves"],
            pp=pdata["pp"],
            status=pdata.get("status"),
            stat_stages=pdata.get("stat_stages", {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
        )
        player_party.append(pkmn)

    enemy_trainer = None
    if "enemy_trainer" in data and data["enemy_trainer"] is not None:
        et = data["enemy_trainer"]
        trainer_party = []
        for pdata in et.get("party", []):
            pkmn = PokemonInstance(
                species=pdata["species"],
                level=pdata["level"],
                hp=pdata["hp"],
                max_hp=pdata["max_hp"],
                attack=pdata["attack"],
                defense=pdata["defense"],
                sp_atk=pdata["sp_atk"],
                sp_def=pdata["sp_def"],
                speed=pdata["speed"],
                moves=pdata["moves"],
                pp=pdata["pp"],
                status=pdata.get("status"),
                stat_stages=pdata.get("stat_stages", {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
            )
            trainer_party.append(pkmn)
        enemy_trainer = Trainer(
            name=et["name"],
            party=trainer_party,
            active_index=et.get("active_index", 0),
            defeated=et.get("defeated", False),
        )

    wild_pokemon = None
    if "wild_pokemon" in data and data["wild_pokemon"] is not None:
        wp = data["wild_pokemon"]
        wild_pokemon = PokemonInstance(
            species=wp["species"],
            level=wp["level"],
            hp=wp["hp"],
            max_hp=wp["max_hp"],
            attack=wp["attack"],
            defense=wp["defense"],
            sp_atk=wp["sp_atk"],
            sp_def=wp["sp_def"],
            speed=wp["speed"],
            moves=wp["moves"],
            pp=wp["pp"],
            status=wp.get("status"),
            stat_stages=wp.get("stat_stages", {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
        )

    map_grid = []
    for row_data in data.get("map_grid", []):
        row = []
        for tile_data in row_data:
            trainer_on_tile = None
            if "trainer" in tile_data and tile_data["trainer"] is not None:
                t = tile_data["trainer"]
                t_party = []
                for pdata in t.get("party", []):
                    pkmn = PokemonInstance(
                        species=pdata["species"],
                        level=pdata["level"],
                        hp=pdata["hp"],
                        max_hp=pdata["max_hp"],
                        attack=pdata["attack"],
                        defense=pdata["defense"],
                        sp_atk=pdata["sp_atk"],
                        sp_def=pdata["sp_def"],
                        speed=pdata["speed"],
                        moves=pdata["moves"],
                        pp=pdata["pp"],
                        status=pdata.get("status"),
                        stat_stages=pdata.get("stat_stages", {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
                    )
                    t_party.append(pkmn)
                trainer_on_tile = Trainer(
                    name=t["name"],
                    party=t_party,
                    active_index=t.get("active_index", 0),
                    defeated=t.get("defeated", False),
                )
            tile = MapTile(
                walkable=tile_data.get("walkable", True),
                has_npc=tile_data.get("has_npc", False),
                npc_name=tile_data.get("npc_name"),
                has_item=tile_data.get("has_item", False),
                item_name=tile_data.get("item_name"),
                is_exit=tile_data.get("is_exit", False),
                is_grass=tile_data.get("is_grass", False),
                trainer=trainer_on_tile,
            )
            row.append(tile)
        map_grid.append(row)

    pos = data.get("player_position", [0, 0])
    facing_str = data.get("player_facing", "DOWN")
    facing = Direction[facing_str] if isinstance(facing_str, str) else Direction.DOWN

    # Parse top-level patrol trainers array (overworld trainers with vision)
    patrol_trainers = []
    for tdata in data.get("trainers", []):
        t_party = []
        for pdata in tdata.get("party", []):
            pkmn = PokemonInstance(
                species=pdata["species"],
                level=pdata["level"],
                hp=pdata["hp"],
                max_hp=pdata["max_hp"],
                attack=pdata.get("attack", 10),
                defense=pdata.get("defense", 10),
                sp_atk=pdata.get("sp_atk", 10),
                sp_def=pdata.get("sp_def", 10),
                speed=pdata.get("speed", 10),
                moves=pdata["moves"],
                pp=pdata.get("pp", [35] * len(pdata["moves"])),
                status=pdata.get("status"),
                stat_stages=pdata.get("stat_stages", {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}),
            )
            t_party.append(pkmn)
        patrol_trainer = Trainer(
            name=tdata["name"],
            party=t_party,
            active_index=tdata.get("active_index", 0),
            defeated=tdata.get("defeated", False),
            position=tdata.get("position"),
            facing=tdata.get("facing", "DOWN"),
            patrol_route=tdata.get("patrol_route"),
            patrol_index=tdata.get("patrol_index", 0),
            vision_range=tdata.get("vision_range", 3),
        )
        patrol_trainers.append(patrol_trainer)

    state = GameState(
        screen=GameScreen(data.get("screen", "overworld")),
        player_party=player_party,
        player_position=(pos[0], pos[1]),
        player_facing=facing,
        map_grid=map_grid,
        map_name=data.get("map_name", ""),
        wild_pokemon=wild_pokemon,
        enemy_trainer=enemy_trainer,
        battle_active=data.get("battle_active", False),
        battle_won=data.get("battle_won"),
        cursor_position=data.get("cursor_position", 0),
        flags=data.get("flags", {}),
        inventory=data.get("inventory", {}),
        badges=data.get("badges", 0),
        action_count=0,
        dialogue_text=data.get("dialogue_text", ""),
        whiteout=False,
        patrol_trainers=patrol_trainers,
    )
    return state


def get_facing_tile_coords(state: GameState) -> tuple[int, int]:
    """Get the coordinates of the tile the player is facing."""
    px, py = state.player_position
    if state.player_facing == Direction.UP:
        return (px, py - 1)
    elif state.player_facing == Direction.DOWN:
        return (px, py + 1)
    elif state.player_facing == Direction.LEFT:
        return (px - 1, py)
    elif state.player_facing == Direction.RIGHT:
        return (px + 1, py)
    return (px, py)


def is_valid_tile(state: GameState, x: int, y: int) -> bool:
    """Check if coordinates are within map bounds."""
    if len(state.map_grid) == 0:
        return False
    if y < 0 or y >= len(state.map_grid):
        return False
    if x < 0 or x >= len(state.map_grid[0]):
        return False
    return True


def _update_trainer_patrol(state: GameState) -> None:
    """Move overworld patrol trainers along their routes each step.

    BUG: Off-by-one in patrol index — advances index BEFORE moving, causing
    the trainer to skip the first tile in their route on the first step and
    wrap to index 0 (start) one step early.
    """
    for trainer in state.patrol_trainers:
        if trainer.defeated:
            continue
        route = trainer.patrol_route
        if not route:
            continue
        idx = trainer.patrol_index
        # BUG: increments index before using it, skipping a tile
        idx = (idx + 1) % len(route)
        trainer.patrol_index = idx
        trainer.position = list(route[idx])


def _check_trainer_vision(state: GameState) -> bool:
    """Check whether any patrol trainer can see the player.

    Returns True and sets battle state if the player enters a trainer's
    3-tile forward vision cone.

    BUG: Uses player facing direction instead of trainer facing direction
    when computing the vision cone, so the cone rotates with the player
    rather than with the trainer.
    """
    px, py = state.player_position
    for trainer in state.patrol_trainers:
        if trainer.defeated:
            continue
        if trainer.position is None:
            continue
        tx, ty = trainer.position[0], trainer.position[1]
        vision_range = trainer.vision_range if trainer.vision_range is not None else 3

        # BUG: should use trainer.facing (Direction[trainer.facing]),
        # but instead uses the player's current facing direction
        facing = state.player_facing  # BUG: wrong — should be Direction[trainer.facing]

        dx, dy = 0, 0
        if facing == Direction.UP:
            dy = -1
        elif facing == Direction.DOWN:
            dy = 1
        elif facing == Direction.LEFT:
            dx = -1
        elif facing == Direction.RIGHT:
            dx = 1

        for dist in range(1, vision_range + 1):
            vx = tx + dx * dist
            vy = ty + dy * dist
            if vx == px and vy == py:
                # Player is in vision cone — trigger battle
                state.enemy_trainer = copy.deepcopy(trainer)
                state.battle_active = True
                state.screen = GameScreen.BATTLE_MAIN
                state.cursor_position = 0
                state.dialogue_text = f"{trainer.name} spotted you!"
                return True
    return False


def _process_overworld(state: GameState, button: Button) -> GameState:
    """Process a button press on the overworld screen."""
    direction_map = {
        Button.UP: Direction.UP,
        Button.DOWN: Direction.DOWN,
        Button.LEFT: Direction.LEFT,
        Button.RIGHT: Direction.RIGHT,
    }

    if button in direction_map:
        new_facing = direction_map[button]
        state.player_facing = new_facing

        dx, dy = 0, 0
        if new_facing == Direction.UP:
            dy = -1
        elif new_facing == Direction.DOWN:
            dy = 1
        elif new_facing == Direction.LEFT:
            dx = -1
        elif new_facing == Direction.RIGHT:
            dx = 1

        px, py = state.player_position
        nx, ny = px + dx, py + dy

        # BUG 1: Movement doesn't check tile walkability.
        # The check below only verifies bounds, not whether the tile is walkable.
        # This means the player can walk through walls and obstacles.
        if is_valid_tile(state, nx, ny):
            state.player_position = (nx, ny)

            # Check for grass encounters, items, exit
            tile = state.map_grid[ny][nx]
            if tile.is_exit:
                state.flags["reached_exit"] = True
            if tile.has_item and tile.item_name:
                state.inventory[tile.item_name] = state.inventory.get(tile.item_name, 0) + 1
                tile.has_item = False
                state.dialogue_text = f"Found {tile.item_name}!"
                state.screen = GameScreen.DIALOGUE
                state.flags[f"picked_up_{tile.item_name}"] = True

        # Update trainer patrol routes each movement step
        _update_trainer_patrol(state)
        # Check trainer line-of-sight vision after movement
        if not state.battle_active:
            _check_trainer_vision(state)

    elif button == Button.A:
        # BUG 4: NPC interaction check uses wrong coordinates.
        # It checks the tile the player is standing ON (px, py)
        # instead of the tile the player is FACING (fx, fy).
        px, py = state.player_position
        # Should be: fx, fy = get_facing_tile_coords(state)
        fx, fy = px, py  # BUG: checks player's own tile

        if is_valid_tile(state, fx, fy):
            tile = state.map_grid[fy][fx]
            if tile.has_npc and tile.npc_name:
                state.dialogue_text = f"{tile.npc_name}: Hello, trainer!"
                state.screen = GameScreen.DIALOGUE
                state.flags[f"talked_to_{tile.npc_name}"] = True
            elif tile.trainer and not tile.trainer.defeated:
                # Start trainer battle
                state.enemy_trainer = copy.deepcopy(tile.trainer)
                state.battle_active = True
                state.screen = GameScreen.BATTLE_MAIN
                state.cursor_position = 0
                state.dialogue_text = f"{tile.trainer.name} wants to battle!"

    elif button == Button.START:
        state.screen = GameScreen.PARTY_MENU
        state.cursor_position = 0

    return state


def _process_battle_main(state: GameState, button: Button) -> GameState:
    """Process button press on the battle main menu.

    Menu options (cursor positions):
      0 = Fight -> go to move select
      1 = Bag   -> go to bag menu
      2 = Pokemon -> go to party menu
      3 = Run   -> attempt to flee
    """
    if button == Button.UP:
        state.cursor_position = max(0, state.cursor_position - 1)
    elif button == Button.DOWN:
        state.cursor_position = min(3, state.cursor_position + 1)
    elif button == Button.A:
        # BUG 3: Pressing A always goes to BATTLE_MOVES regardless of cursor.
        # It should check cursor_position: 0=Fight, 1=Bag, 2=Pokemon, 3=Run.
        # Instead, it unconditionally transitions to move selection.
        state.screen = GameScreen.BATTLE_MOVES
        state.cursor_position = 0
    elif button == Button.B:
        pass  # Can't back out of battle main menu

    return state


def _process_battle_moves(state: GameState, button: Button) -> GameState:
    """Process button press on the move selection screen."""
    player_pkmn = state.player_party[0]
    num_moves = len(player_pkmn.moves)

    if button == Button.UP:
        state.cursor_position = max(0, state.cursor_position - 1)
    elif button == Button.DOWN:
        state.cursor_position = min(num_moves - 1, state.cursor_position + 1)
    elif button == Button.B:
        state.screen = GameScreen.BATTLE_MAIN
        state.cursor_position = 0
    elif button == Button.A:
        move_index = state.cursor_position

        # Check PP
        if player_pkmn.pp[move_index] <= 0:
            return state

        # Determine enemy
        enemy_pkmn = None
        if state.enemy_trainer:
            enemy_pkmn = state.enemy_trainer.party[state.enemy_trainer.active_index]
        elif state.wild_pokemon:
            enemy_pkmn = state.wild_pokemon

        if enemy_pkmn is None:
            return state

        enemy_move_index = select_enemy_move(enemy_pkmn)

        # BUG 5: Turn order doesn't account for active Pokemon.
        # It always uses player_party[0].speed for turn order comparison,
        # but get_turn_order correctly uses player_party[0].
        # The real bug: we pass the FULL party to get_turn_order, and it uses
        # party[0] — but if the active index is different (e.g., after a switch),
        # it still checks party[0]'s speed instead of the actual active Pokemon.
        turn_order = get_turn_order(
            state.player_party, enemy_pkmn, move_index, enemy_move_index
        )

        # Execute turns
        for side, attacker, defender, m_idx in turn_order:
            if attacker.hp <= 0:
                continue
            execute_move(attacker, defender, m_idx)
            if check_faint(defender):
                defender.hp = 0
                break

        # Apply end-of-turn effects
        apply_end_of_turn_effects(player_pkmn)
        if enemy_pkmn:
            apply_end_of_turn_effects(enemy_pkmn)

        # Check battle end conditions
        if check_faint(enemy_pkmn):
            enemy_pkmn.hp = 0
            if state.enemy_trainer:
                # Check if trainer has more Pokemon
                all_fainted = True
                for i, p in enumerate(state.enemy_trainer.party):
                    if p.hp > 0 and i != state.enemy_trainer.active_index:
                        state.enemy_trainer.active_index = i
                        all_fainted = False
                        break
                if all_fainted:
                    state.enemy_trainer.defeated = True
                    state.battle_active = False
                    state.battle_won = True
                    state.screen = GameScreen.DIALOGUE
                    state.dialogue_text = f"Defeated {state.enemy_trainer.name}!"
                    # Mark trainer as defeated on the map tile
                    _mark_trainer_defeated(state, state.enemy_trainer.name)
            else:
                # Wild pokemon fainted
                state.battle_active = False
                state.battle_won = True
                state.screen = GameScreen.OVERWORLD
        elif check_faint(player_pkmn):
            player_pkmn.hp = 0
            # Check if player has more Pokemon
            switched = False
            for i, p in enumerate(state.player_party):
                if p.hp > 0 and i != 0:
                    # Swap to front
                    state.player_party[0], state.player_party[i] = state.player_party[i], state.player_party[0]
                    state.screen = GameScreen.BATTLE_MAIN
                    state.cursor_position = 0
                    switched = True
                    break
            if not switched:
                state.whiteout = True
                state.battle_active = False
                state.battle_won = False
                state.screen = GameScreen.OVERWORLD
        else:
            state.screen = GameScreen.BATTLE_MAIN
            state.cursor_position = 0

    return state


def _mark_trainer_defeated(state: GameState, trainer_name: str) -> None:
    """Mark a trainer as defeated on the map grid and in patrol trainers list."""
    for row in state.map_grid:
        for tile in row:
            if tile.trainer and tile.trainer.name == trainer_name:
                tile.trainer.defeated = True
    for trainer in state.patrol_trainers:
        if trainer.name == trainer_name:
            trainer.defeated = True


def _process_battle_switch(state: GameState, button: Button) -> GameState:
    """Process button press on the battle switch (party) screen."""
    num_pokemon = len(state.player_party)

    if button == Button.UP:
        state.cursor_position = max(0, state.cursor_position - 1)
    elif button == Button.DOWN:
        state.cursor_position = min(num_pokemon - 1, state.cursor_position + 1)
    elif button == Button.B:
        state.screen = GameScreen.BATTLE_MAIN
        state.cursor_position = 0
    elif button == Button.A:
        target = state.cursor_position
        if target != 0 and state.player_party[target].hp > 0:
            # Swap selected Pokemon to front
            state.player_party[0], state.player_party[target] = (
                state.player_party[target],
                state.player_party[0],
            )
            # Enemy gets a free turn
            enemy_pkmn = None
            if state.enemy_trainer:
                enemy_pkmn = state.enemy_trainer.party[state.enemy_trainer.active_index]
            elif state.wild_pokemon:
                enemy_pkmn = state.wild_pokemon

            if enemy_pkmn and enemy_pkmn.hp > 0:
                enemy_move_index = select_enemy_move(enemy_pkmn)
                execute_move(enemy_pkmn, state.player_party[0], enemy_move_index)

            state.screen = GameScreen.BATTLE_MAIN
            state.cursor_position = 0

    return state


def _process_dialogue(state: GameState, button: Button) -> GameState:
    """Process button press on dialogue screen."""
    if button == Button.A or button == Button.B:
        state.dialogue_text = ""
        if state.battle_active:
            state.screen = GameScreen.BATTLE_MAIN
            state.cursor_position = 0
        elif state.battle_won is True:
            # Post-battle: check for badge awarding
            if state.enemy_trainer and "Gym Leader" in state.flags.get("battle_context", ""):
                state.badges += 1
                state.flags["badge_obtained"] = True
            state.battle_won = None
            state.enemy_trainer = None
            state.screen = GameScreen.OVERWORLD
        else:
            state.screen = GameScreen.OVERWORLD
    return state


def _process_bag_menu(state: GameState, button: Button) -> GameState:
    """Process button press on bag menu screen."""
    items = list(state.inventory.items())
    num_items = len(items)

    if button == Button.UP:
        state.cursor_position = max(0, state.cursor_position - 1)
    elif button == Button.DOWN:
        state.cursor_position = min(max(0, num_items - 1), state.cursor_position + 1)
    elif button == Button.B:
        if state.battle_active:
            state.screen = GameScreen.BATTLE_MAIN
        else:
            state.screen = GameScreen.OVERWORLD
        state.cursor_position = 0
    elif button == Button.A and num_items > 0:
        item_name, count = items[state.cursor_position]
        if state.battle_active and item_name in ("Potion", "Super Potion"):
            # Use healing item on active Pokemon
            player_pkmn = state.player_party[0]
            if item_name == "Potion":
                player_pkmn.hp = min(player_pkmn.max_hp, player_pkmn.hp + 20)
            elif item_name == "Super Potion":
                player_pkmn.hp = min(player_pkmn.max_hp, player_pkmn.hp + 50)
            state.inventory[item_name] -= 1
            if state.inventory[item_name] <= 0:
                del state.inventory[item_name]

            # Enemy gets a free turn after item use
            enemy_pkmn = None
            if state.enemy_trainer:
                enemy_pkmn = state.enemy_trainer.party[state.enemy_trainer.active_index]
            elif state.wild_pokemon:
                enemy_pkmn = state.wild_pokemon

            if enemy_pkmn and enemy_pkmn.hp > 0:
                enemy_move_index = select_enemy_move(enemy_pkmn)
                execute_move(enemy_pkmn, player_pkmn, enemy_move_index)

            state.screen = GameScreen.BATTLE_MAIN
            state.cursor_position = 0

    return state


def _process_party_menu(state: GameState, button: Button) -> GameState:
    """Process button press on party menu screen (non-battle)."""
    num_pokemon = len(state.player_party)

    if button == Button.UP:
        state.cursor_position = max(0, state.cursor_position - 1)
    elif button == Button.DOWN:
        state.cursor_position = min(num_pokemon - 1, state.cursor_position + 1)
    elif button == Button.B:
        state.screen = GameScreen.OVERWORLD
        state.cursor_position = 0
    elif button == Button.A:
        # View Pokemon details (simplified: just show summary)
        pass

    return state


def _process_yes_no(state: GameState, button: Button) -> GameState:
    """Process button press on yes/no prompt."""
    if button == Button.UP:
        state.cursor_position = max(0, state.cursor_position - 1)
    elif button == Button.DOWN:
        state.cursor_position = min(1, state.cursor_position + 1)
    elif button == Button.A:
        if state.cursor_position == 0:
            state.flags["yes_no_answer"] = "yes"
        else:
            state.flags["yes_no_answer"] = "no"
        state.screen = GameScreen.OVERWORLD
        state.dialogue_text = ""
    elif button == Button.B:
        state.flags["yes_no_answer"] = "no"
        state.screen = GameScreen.OVERWORLD
        state.dialogue_text = ""
    return state


def process_input(state: GameState, button: Button) -> GameState:
    """Process a single button press and return the updated game state."""
    state.action_count += 1

    handlers = {
        GameScreen.OVERWORLD: _process_overworld,
        GameScreen.BATTLE_MAIN: _process_battle_main,
        GameScreen.BATTLE_MOVES: _process_battle_moves,
        GameScreen.BATTLE_SWITCH: _process_battle_switch,
        GameScreen.DIALOGUE: _process_dialogue,
        GameScreen.BAG_MENU: _process_bag_menu,
        GameScreen.PARTY_MENU: _process_party_menu,
        GameScreen.YES_NO_PROMPT: _process_yes_no,
    }

    handler = handlers.get(state.screen)
    if handler:
        state = handler(state, button)

    return state


def replay_actions(state: GameState, actions: list[str]) -> GameState:
    """Replay a list of button press strings against the game state."""
    for action_str in actions:
        button = Button[action_str]
        state = process_input(state, button)
    return state


def state_to_dict(state: GameState) -> dict:
    """Serialize GameState to a JSON-serializable dict."""
    def pokemon_to_dict(p: PokemonInstance) -> dict:
        return {
            "species": p.species,
            "level": p.level,
            "hp": p.hp,
            "max_hp": p.max_hp,
            "attack": p.attack,
            "defense": p.defense,
            "sp_atk": p.sp_atk,
            "sp_def": p.sp_def,
            "speed": p.speed,
            "moves": p.moves,
            "pp": list(p.pp),
            "status": p.status,
            "stat_stages": dict(p.stat_stages),
        }

    def trainer_to_dict(t: Trainer) -> dict:
        return {
            "name": t.name,
            "party": [pokemon_to_dict(p) for p in t.party],
            "active_index": t.active_index,
            "defeated": t.defeated,
        }

    result = {
        "screen": state.screen.value,
        "player_party": [pokemon_to_dict(p) for p in state.player_party],
        "player_position": list(state.player_position),
        "player_facing": state.player_facing.value,
        "map_name": state.map_name,
        "battle_active": state.battle_active,
        "battle_won": state.battle_won,
        "cursor_position": state.cursor_position,
        "flags": dict(state.flags),
        "inventory": dict(state.inventory),
        "badges": state.badges,
        "action_count": state.action_count,
        "dialogue_text": state.dialogue_text,
        "whiteout": state.whiteout,
    }

    if state.enemy_trainer:
        result["enemy_trainer"] = trainer_to_dict(state.enemy_trainer)
    else:
        result["enemy_trainer"] = None

    if state.wild_pokemon:
        result["wild_pokemon"] = pokemon_to_dict(state.wild_pokemon)
    else:
        result["wild_pokemon"] = None

    return result
