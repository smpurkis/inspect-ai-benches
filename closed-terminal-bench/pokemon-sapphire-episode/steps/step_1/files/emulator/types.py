"""Game state types for Pokemon Sapphire mock emulator."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GameScreen(Enum):
    OVERWORLD = "overworld"
    BATTLE_MAIN = "battle_main"
    BATTLE_MOVES = "battle_moves"
    BATTLE_SWITCH = "battle_switch"
    BAG_MENU = "bag_menu"
    PARTY_MENU = "party_menu"
    DIALOGUE = "dialogue"
    YES_NO_PROMPT = "yes_no_prompt"


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class Button(Enum):
    A = "A"
    B = "B"
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    START = "START"
    SELECT = "SELECT"


@dataclass
class PokemonInstance:
    species: str
    level: int
    hp: int
    max_hp: int
    attack: int
    defense: int
    sp_atk: int
    sp_def: int
    speed: int
    moves: list[str]
    pp: list[int]
    status: Optional[str] = None  # poison, burn, paralyze, sleep, freeze
    stat_stages: dict = field(
        default_factory=lambda: {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    )


@dataclass
class Trainer:
    name: str
    party: list[PokemonInstance]
    active_index: int = 0
    defeated: bool = False
    # Overworld patrol fields (optional; None when not a patrol trainer)
    position: Optional[list] = None          # current [x, y] on map
    facing: Optional[str] = None             # "UP"/"DOWN"/"LEFT"/"RIGHT"
    patrol_route: Optional[list] = None      # list of [x, y] waypoints
    patrol_index: int = 0                    # current waypoint index
    vision_range: int = 3                    # tiles ahead trainer can see


@dataclass
class MapTile:
    walkable: bool = True
    has_npc: bool = False
    npc_name: Optional[str] = None
    has_item: bool = False
    item_name: Optional[str] = None
    is_exit: bool = False
    is_grass: bool = False
    trainer: Optional[Trainer] = None


@dataclass
class GameState:
    screen: GameScreen
    player_party: list[PokemonInstance]
    player_position: tuple[int, int] = (0, 0)
    player_facing: Direction = Direction.DOWN
    map_grid: list[list[MapTile]] = field(default_factory=list)
    map_name: str = ""
    # Battle state
    wild_pokemon: Optional[PokemonInstance] = None
    enemy_trainer: Optional[Trainer] = None
    battle_active: bool = False
    battle_won: Optional[bool] = None
    cursor_position: int = 0
    # Flags
    flags: dict = field(default_factory=dict)
    inventory: dict = field(default_factory=dict)
    badges: int = 0
    action_count: int = 0
    dialogue_text: str = ""
    whiteout: bool = False
    # Overworld patrol trainers (separate from map tile trainers)
    patrol_trainers: list = field(default_factory=list)
