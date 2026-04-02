# Step 1: Fix the Core 1v1 Battle Engine

The file `/app/step_1/files/battle_engine.py` contains a deterministic Pokemon-style text battle engine. However, it has several bugs that cause incorrect behavior. Your task is to find and fix all bugs so the engine correctly:

1. Loads scenario JSON files and creates Pokemon with accurate stats
2. Executes turn-by-turn battles with correct damage calculation
3. Applies type effectiveness properly (e.g., Electric is super effective vs Water)
4. Determines turn order correctly (faster Pokemon moves first)
5. Ends battles properly when a Pokemon faints
6. Produces deterministic output for a given RNG seed

## Key Files

- `/app/step_1/files/battle_engine.py` — The broken engine (fix this)
- `/app/step_1/files/models.py` — Data classes (Pokemon, Move, TurnResult, BattleState)
- `/app/step_1/files/data/species.json` — Pokemon species with base stats
- `/app/step_1/files/data/moves.json` — Move definitions (type, power, accuracy, etc.)
- `/app/step_1/files/data/type_chart.json` — Type effectiveness chart (attacking_type → defending_type → multiplier)
- `/app/step_1/files/data/scenario_public_01.json` — Test scenario: Pikachu vs Squirtle
- `/app/step_1/files/data/expected_output_01.json` — Expected properties of the output

## Damage Formula Reference

The engine uses the standard Pokemon damage formula:

```
base = ((2 * level / 5 + 2) * power * attack_stat / defense_stat) / 50 + 2
damage = floor(base * STAB * type_effectiveness * random_factor)
```

- **STAB** (Same-Type Attack Bonus): 1.5x if the move's type matches one of the attacker's types, otherwise 1.0x
- **Type effectiveness**: Looked up from `type_chart.json` as `chart[move_type][defender_type]`; multiply together for dual-typed defenders; missing entries default to 1.0x
- **Random factor**: `randint(85, 100) / 100` from the battle's seeded RNG
- **Modifier combination**: `STAB * type_effectiveness` (multiplied, not added)
- Immune matchups (0x effectiveness) always deal 0 damage
- Otherwise minimum 1 damage

## HP Formula Reference

```
HP  = floor((2 * base + IV + EV/4) * level / 100) + level + 10
Other = floor((2 * base + IV + EV/4) * level / 100) + 5
```

IVs and EVs are 0 in this engine (simplified).

## Turn Order

1. Check move priority (higher priority moves go first)
2. Among equal priority, the faster Pokemon (higher Speed stat) goes first
3. Speed ties are broken by a deterministic RNG coin flip

## Battle Flow

Each turn:
1. Both sides select moves
2. Determine attack order
3. First Pokemon attacks; if defender faints (HP ≤ 0), the battle ends immediately
4. If defender survived, second Pokemon attacks
5. Check for faints after the turn

## Verification

Run the visible tests to check your fixes:

```bash
python3 -m pytest /app/step_1/files/tests.py -v
```

Do NOT use `python3 tests.py` — test files require pytest.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
