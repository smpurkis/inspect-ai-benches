# Step 2: Status Conditions, Stat Stages, and Switching

Extend the battle engine to support status conditions, stat stage modifiers, and Pokemon switching.

## Status Conditions

Implement these status conditions:

| Status | Effect |
|--------|--------|
| **poison** | Deals 1/8 of max HP at end of each turn (rounded down, minimum 1) |
| **burn** | Deals 1/8 of max HP at end of turn AND halves physical attack damage |
| **paralysis** | Speed is quartered (floor division); 25% chance each turn of being unable to move |
| **sleep** | Pokemon cannot attack; wakes up after 1-3 turns (determined by RNG on infliction) |
| **freeze** | Pokemon cannot attack; 20% chance of thawing at the start of each turn |

Status moves (Toxic, Will-O-Wisp, Thunder Wave, Hypnosis) inflict the condition specified in their `effect` field. A Pokemon can only have one status at a time; attempting to inflict a second status fails.

Poison/burn end-of-turn damage can KO a Pokemon.

## Stat Stages

Implement stat stage modifiers (-6 to +6):

| Stage | Multiplier |
|-------|-----------|
| -6 | 2/8 = 0.25 |
| -5 | 2/7 ≈ 0.286 |
| -4 | 2/6 ≈ 0.333 |
| -3 | 2/5 = 0.4 |
| -2 | 2/4 = 0.5 |
| -1 | 2/3 ≈ 0.667 |
| 0 | 1.0 |
| +1 | 3/2 = 1.5 |
| +2 | 4/2 = 2.0 |
| +3 | 5/2 = 2.5 |
| +4 | 6/2 = 3.0 |
| +5 | 7/2 = 3.5 |
| +6 | 8/2 = 4.0 |

Formula: `multiplier = (2 + stage) / 2` if stage >= 0, else `2 / (2 + abs(stage))`

Stat stages clamp at -6 and +6. Moves like Swords Dance raise the specified stat by the number of stages in their effect. The stat multiplier is applied to the relevant stat during damage calculation.

## Switching

When a scenario uses the extended action format, support switching:

```json
{"pokemon_1": {"action": "switch", "target": 0}, "pokemon_2": {"action": "move", "move": "Water Gun"}}
```

- `"target"` is the index into the party array
- Switching happens BEFORE attacks (switch priority)
- The active Pokemon is swapped with the party member
- Switching resets all stat stages to 0
- When the active Pokemon faints, the trainer must switch to a non-fainted party member

## Move Choice Format

The engine should support both the Step 1 format (simple strings) and the extended format:
- Simple: `{"pokemon_1": "Thunderbolt", "pokemon_2": "Water Gun"}`
- Extended: `{"pokemon_1": {"action": "move", "move": "Thunderbolt"}, "pokemon_2": {"action": "move", "move": "Water Gun"}}`

## Party Format

When a Pokemon entry has a `"party"` field, it's an array of additional Pokemon:

```json
{
  "species": "Charmander",
  "level": 50,
  "moves": ["Flamethrower"],
  "party": [
    {"species": "Pikachu", "level": 50, "moves": ["Thunderbolt"]}
  ]
}
```

## Key Files

- `/app/step_2/files/data/scenario_poison.json` — Poison scenario
- `/app/step_2/files/data/scenario_switch.json` — Switching scenario

## Verification

```bash
python3 -m pytest /app/step_2/files/tests.py -v
```

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
- Extend `battle_engine.py` and `models.py` as needed.
