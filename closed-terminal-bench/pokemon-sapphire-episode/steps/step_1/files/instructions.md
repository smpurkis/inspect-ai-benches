# Pokemon Sapphire Episode — Step 1: Battle Tactics

Fix the broken game engine so it correctly simulates Pokemon battles.

## Context

You have a text-based mock Pokemon game engine in `/app/step_1/files/emulator/`. The engine loads savestate JSON files and processes button presses to simulate game mechanics. However, `game_engine.py` and `battle_system.py` contain bugs that cause incorrect behavior.

The following files are **working** and should not need modification:
- `emulator/types.py` — Data classes for game state
- `emulator/constants.py` — Type chart, species data, move data
- `emulator/renderer.py` — Text rendering of game state

The following files are **broken** and need to be fixed:
- `emulator/game_engine.py` — Main engine (screen transitions, overworld, input handling)
- `emulator/battle_system.py` — Battle damage calculation and turn execution

## Requirements

1. Fix all bugs in `game_engine.py` and `battle_system.py`
2. The engine must load battle savestates and process action sequences correctly
3. Battle damage must follow the standard Gen III Pokemon damage formula
4. Type effectiveness must be applied correctly (multiplicatively for dual-type defenders)
5. Turn order must respect move priority, then speed of the actual active Pokemon
6. Faint detection must happen after damage is applied, not before
7. The engine must be deterministic — same inputs always produce same outputs

## Architecture

The engine processes one button press at a time:
- `load_savestate(path)` → `GameState`
- `process_input(state, button)` → updated `GameState`
- `replay_actions(state, actions)` → final `GameState`
- `state_to_dict(state)` → JSON-serializable dict

Battle flow: `BATTLE_MAIN` (Fight/Bag/Pokemon/Run) → `BATTLE_MOVES` (select move) → execute turn → back to `BATTLE_MAIN`

## Verification

Tests at `/app/step_1/files/tests.py`

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic
- Do not modify test files or reference files
- Only modify files in the `emulator/` directory
