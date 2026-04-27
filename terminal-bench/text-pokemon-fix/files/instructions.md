# Fix the Core 1v1 Battle Engine

The file `/app/files/battle_engine.py` contains a deterministic Pokemon-style text battle engine. However, it has several bugs that cause incorrect behavior. Your task is to find and fix all bugs so the engine correctly:

1. Loads scenario JSON files and creates Pokemon with accurate stats
2. Executes turn-by-turn battles with correct damage calculation
3. Applies type effectiveness properly (e.g., Electric is super effective vs Water)
4. Determines turn order correctly (faster Pokemon moves first)
5. Ends battles properly when a Pokemon faints
6. Produces deterministic output for a given RNG seed

## Important

- **Fix the bugs** in the existing code — do not rewrite the engine from scratch.
- **Keep all function names and signatures unchanged** — the tests import specific functions by name:
  `run_battle`, `calculate_damage`, `create_pokemon`, `get_type_effectiveness`,
  `determine_turn_order`, `calculate_stat`, `load_species_db`, `load_moves_db`, `load_type_chart`,
  `execute_attack`

## Key Files

- `/app/files/battle_engine.py` — The broken engine (fix this)
- `/app/files/models.py` — Data classes (Pokemon, Move, TurnResult, BattleState)
- `/app/files/data/species.json` — Pokemon species with base stats
- `/app/files/data/moves.json` — Move definitions (type, power, accuracy, etc.)
- `/app/files/data/type_chart.json` — Type effectiveness chart (attacking_type → defending_type → multiplier)
- `/app/files/data/scenario_public_01.json` — Test scenario: Pikachu vs Squirtle
- `/app/files/data/expected_output_01.json` — Expected properties of the output

## Damage Calculation

Damage follows the standard Pokemon Gen III formula. The calculation involves the attacker's level, move power, attack/defense stats, and various multipliers. Consult the code structure for specifics.

- **STAB** (Same-Type Attack Bonus): Applied when the move's type matches the attacker's type
- **Type effectiveness**: Looked up from `type_chart.json` using the move type and defender type(s); multiply together for dual-typed defenders; missing entries default to neutral
- **Random factor**: A random factor between 0.8 and 1.0 is applied to each damage roll
- Immune matchups (0x effectiveness) always deal 0 damage
- Otherwise minimum 1 damage

## Stat Calculation

HP calculation follows the standard formula incorporating base stats, IVs, and EVs. Other stats use a similar but slightly different formula. IVs and EVs are 0 in this engine (simplified).

Stat stage modifiers (from moves like Swords Dance) should affect the relevant stat during damage calculation using the standard Gen III stage multiplier table.

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

## PP (Power Points)

Each move has limited PP. Using a move costs 1 PP. When a move's PP reaches 0, it cannot be selected. If all of a Pokemon's moves have 0 PP remaining, it uses **Struggle** — a typeless recoil move that damages both the target and the user.

## Verification

Run the visible tests to check your fixes:

```bash
python3 -m pytest /app/files/tests.py -v
```

Do NOT use `python3 tests.py` — test files require pytest.

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
