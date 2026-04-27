# Pokemon Battle Engine — Bug Fixing

A text-based Pokemon battle engine in `/app/files/emulator/` has multiple bugs across its source files. The engine loads savestate JSON files and processes button-press sequences to simulate Gen III Pokemon battles. Your job is to find and fix every bug so the engine produces correct, deterministic results.

## Files

- `emulator/types.py` — Data classes (working, do not modify)
- `emulator/constants.py` — Type chart, species data, move data (working, do not modify)
- `emulator/renderer.py` — Text rendering (working, do not modify)
- `emulator/game_engine.py` — Main engine: screen transitions, input handling, battle flow
- `emulator/battle_system.py` — Damage calculation, move execution, turn ordering

Bugs exist in `game_engine.py` and `battle_system.py`. Read the code carefully, trace through the logic, and compare behavior against how Gen III Pokemon mechanics actually work.

## Verification

    python3 -m pytest /app/files/tests.py -v

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic (no randomness)
- Do not modify test files, reference files, types.py, constants.py, or renderer.py
- Only modify files in the `emulator/` directory
