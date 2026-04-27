"""Text renderer for game state observations."""

from .types import GameScreen, GameState, PokemonInstance
from .constants import MOVE_DATA


def render_pokemon_summary(pkmn: PokemonInstance, prefix: str = "") -> str:
    """Render a one-line Pokemon summary."""
    status_str = f" [{pkmn.status.upper()}]" if pkmn.status else ""
    return f"{prefix}{pkmn.species} (Lv.{pkmn.level}) HP: {pkmn.hp}/{pkmn.max_hp}{status_str}"


def render_battle_main(state: GameState) -> str:
    """Render the battle main menu screen."""
    lines = ["=== BATTLE ==="]

    player_pkmn = state.player_party[0]
    lines.append(render_pokemon_summary(player_pkmn, "Your "))

    if state.enemy_trainer:
        enemy = state.enemy_trainer
        enemy_pkmn = enemy.party[enemy.active_index]
        lines.append(render_pokemon_summary(enemy_pkmn, f"Enemy {enemy.name}'s "))
    elif state.wild_pokemon:
        lines.append(render_pokemon_summary(state.wild_pokemon, "Wild "))

    lines.append("")
    options = ["Fight", "Bag", "Pokemon", "Run"]
    for i, opt in enumerate(options):
        marker = ">" if i == state.cursor_position else " "
        lines.append(f"  {marker} {i + 1}. {opt}")

    lines.append("")
    lines.append("[A] Select  [B] Back  [UP/DOWN] Navigate")
    return "\n".join(lines)


def render_battle_moves(state: GameState) -> str:
    """Render the move selection screen."""
    lines = ["=== MOVES ==="]

    player_pkmn = state.player_party[0]
    lines.append(render_pokemon_summary(player_pkmn, "Your "))
    lines.append("")

    for i, move_name in enumerate(player_pkmn.moves):
        move_info = MOVE_DATA.get(move_name, {})
        move_type = move_info.get("type", "???")
        pp = player_pkmn.pp[i] if i < len(player_pkmn.pp) else 0
        max_pp = move_info.get("pp", 0)
        marker = ">" if i == state.cursor_position else " "
        lines.append(f"  {marker} {i + 1}. {move_name} ({move_type}) PP: {pp}/{max_pp}")

    lines.append("")
    lines.append("[A] Select  [B] Back  [UP/DOWN] Navigate")
    return "\n".join(lines)


def render_overworld(state: GameState) -> str:
    """Render the overworld screen."""
    lines = [f"=== {state.map_name.upper()} ==="]
    lines.append(f"Position: ({state.player_position[0]}, {state.player_position[1]})")
    lines.append(f"Facing: {state.player_facing.value}")
    lines.append("")

    # Render mini-map (5x5 around player)
    px, py = state.player_position
    for dy in range(-2, 3):
        row = ""
        for dx in range(-2, 3):
            mx, my = px + dx, py + dy
            if dx == 0 and dy == 0:
                row += "@"
            elif 0 <= my < len(state.map_grid) and 0 <= mx < len(state.map_grid[0]):
                tile = state.map_grid[my][mx]
                if not tile.walkable:
                    row += "#"
                elif tile.has_npc:
                    row += "N"
                elif tile.has_item:
                    row += "!"
                elif tile.is_exit:
                    row += "E"
                elif tile.is_grass:
                    row += "~"
                else:
                    row += "."
            else:
                row += " "
        lines.append(f"  {row}")

    lines.append("")
    lines.append("[D-PAD] Move  [A] Interact  [START] Menu")
    return "\n".join(lines)


def render_dialogue(state: GameState) -> str:
    """Render dialogue screen."""
    lines = ["=== DIALOGUE ==="]
    lines.append("")
    lines.append(state.dialogue_text)
    lines.append("")
    lines.append("[A] Continue  [B] Skip")
    return "\n".join(lines)


def render_party_menu(state: GameState) -> str:
    """Render party menu screen."""
    lines = ["=== PARTY ==="]
    for i, pkmn in enumerate(state.player_party):
        marker = ">" if i == state.cursor_position else " "
        lines.append(f"  {marker} {render_pokemon_summary(pkmn)}")
    lines.append("")
    lines.append("[A] Select  [B] Back  [UP/DOWN] Navigate")
    return "\n".join(lines)


def render_bag_menu(state: GameState) -> str:
    """Render bag menu screen."""
    lines = ["=== BAG ==="]
    items = list(state.inventory.items())
    if not items:
        lines.append("  (Empty)")
    else:
        for i, (item_name, count) in enumerate(items):
            marker = ">" if i == state.cursor_position else " "
            lines.append(f"  {marker} {item_name} x{count}")
    lines.append("")
    lines.append("[A] Use  [B] Back  [UP/DOWN] Navigate")
    return "\n".join(lines)


def render_yes_no(state: GameState) -> str:
    """Render yes/no prompt."""
    lines = ["=== PROMPT ==="]
    lines.append(state.dialogue_text)
    lines.append("")
    options = ["Yes", "No"]
    for i, opt in enumerate(options):
        marker = ">" if i == state.cursor_position else " "
        lines.append(f"  {marker} {opt}")
    lines.append("")
    lines.append("[A] Select  [UP/DOWN] Navigate")
    return "\n".join(lines)


def render(state: GameState) -> str:
    """Render the current game state as a text observation."""
    renderers = {
        GameScreen.BATTLE_MAIN: render_battle_main,
        GameScreen.BATTLE_MOVES: render_battle_moves,
        GameScreen.OVERWORLD: render_overworld,
        GameScreen.DIALOGUE: render_dialogue,
        GameScreen.PARTY_MENU: render_party_menu,
        GameScreen.BATTLE_SWITCH: render_party_menu,
        GameScreen.BAG_MENU: render_bag_menu,
        GameScreen.YES_NO_PROMPT: render_yes_no,
    }
    renderer_fn = renderers.get(state.screen, render_overworld)
    return renderer_fn(state)
