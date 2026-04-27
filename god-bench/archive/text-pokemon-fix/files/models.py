"""Data classes for the Pokemon battle engine."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Move:
    name: str
    type: str
    category: str  # "physical", "special", "status"
    power: int
    accuracy: int
    pp: int
    current_pp: int
    priority: int = 0
    effect: Optional[dict] = None


@dataclass
class Pokemon:
    name: str
    types: list
    stats: dict
    moves: list
    current_hp: int
    status: Optional[str] = None
    status_turns: int = 0
    stat_stages: dict = field(default_factory=lambda: {
        "attack": 0, "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0,
    })


@dataclass
class TurnResult:
    attacker: str
    move: str
    damage: int
    defender_hp_after: int
    effectiveness: str
    critical: bool = False
    message: str = ""


@dataclass
class BattleState:
    pokemon_1: Pokemon = None
    pokemon_2: Pokemon = None
    party_1: list = field(default_factory=list)
    party_2: list = field(default_factory=list)
    turn_count: int = 0
    weather: Optional[str] = None
    weather_turns: int = 0
    winner: Optional[str] = None
