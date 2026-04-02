# Pokemon Sapphire Episode — Step 2: Trainer Patrol and Line-of-Sight

Fix trainer patrol route mechanics and vision cone detection, then navigate Route 106 past Youngster Jake.

## Context

Building on Step 1's battle fixes, the engine now has overworld trainers that patrol routes and
can spot the player with a forward vision cone. Both systems have bugs that must be corrected.

The emulator files are at `/app/step_1/files/emulator/` (same files you fixed in Step 1).

## Bugs to Fix

### Bug A — Patrol index off-by-one (`_update_trainer_patrol` in `game_engine.py`)

The trainer patrol function increments the patrol index **before** using it to select the next
waypoint. This causes trainers to skip the first waypoint in their route on the first step and
wrap around one step early.

Fix: read the current index, move the trainer to `route[index]`, then increment for the next call.

### Bug B — Vision cone uses player facing instead of trainer facing (`_check_trainer_vision`)

The vision cone calculation uses `state.player_facing` (the direction the **player** is facing)
instead of `Direction[trainer.facing]` (the direction the **trainer** is facing). This means the
vision cone rotates with the player rather than with the trainer.

Fix: replace `state.player_facing` with `Direction[trainer.facing]` when computing the cone
direction vectors.

## Map Layout

Route 106 is a 10x8 grid. Player starts at `[1, 6]` facing UP. Exit tile is at `[8, 1]`.

Youngster Jake patrols the route:
- Starting position: `[3, 4]`, facing: `DOWN`
- Patrol waypoints: `[3,3] → [3,4] → [3,5] → [3,4]` (loops)
- Vision range: 3 tiles ahead in his facing direction (DOWN = tiles at y+1, y+2, y+3)
- Party: Zigzagoon Lv.8

Entering Jake's 3-tile forward vision cone triggers a trainer battle. Approaching from his side
(columns other than 3, or from above while he faces down) avoids his vision — this is the
"blind spot" path.

## Requirements

1. Fix both bugs in `game_engine.py`
2. Write `/app/step_2/files/solution_actions_step2.json` — a JSON array of button-press strings
   that navigates from `[1,6]` to the exit at `[8,1]`. The sequence must either:
   - Defeat Youngster Jake before passing through his zone, OR
   - Pass through his blind spot (approach from a column he is not watching)
3. Trainer vision must trigger a battle when player enters the 3-tile forward cone
4. Approaching from the side (blind spot) must not trigger a battle
5. Youngster Jake blocks the direct center path until defeated
6. Action count must be <= 200

## Verification

Tests at `/app/step_2/files/tests.py`

    python3 -m pytest /app/step_2/files/tests.py -v

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic
- Do not modify test files or reference files
