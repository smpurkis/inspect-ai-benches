# Pokemon Sapphire Episode — Step 3: Unknown Gym Challenge

Complete the Dewford Gym challenge without any hints about the map layout, your party, or the trainers you will face.

## Context

Using the fixed game engine from Steps 1 and 2, you must write an action sequence that clears the
Dewford Gym. Unlike previous steps, no information about your party, trainer levels, or gym layout
is provided in advance.

The gym savestate is at `/app/step_3/files/savestates/gym_visible.json`.

## Requirements

1. Write an action sequence file at `/app/step_3/files/solution_actions.json` containing a JSON
   array of button-press strings (e.g., `["UP", "UP", "RIGHT", "A", "A", ...]`).
2. The action sequence must:
   - Defeat all trainers in the gym, including the Gym Leader
   - Result in `"Leader Brawly"` appearing in the set of defeated trainer names
   - Earn at least one badge (`badges >= 1` OR `flags["badge_obtained"] == True`)
3. No whiteout — the player's party must not be completely wiped out
4. Use at most 600 actions total

## Discovering the gym

Your party and the gym layout are unknown — discover them by exploration.

- Explore the gym by attempting moves and observing whether your position changes to infer walls
- Attempt to interact with trainers (press A while facing them) to initiate battles
- Pick move slots strategically — consider which moves might be effective given what you observe
- If a move attempt has no PP remaining, it will not execute; track your PP usage

The first 20 actions in your solution must include at least one directional move (UP, DOWN, LEFT,
or RIGHT) before any A press. Immediately pressing A without exploring is not valid.

## Verification

Tests at `/app/step_3/files/tests.py`

    python3 -m pytest /app/step_3/files/tests.py -v

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container
- Keep outputs deterministic
- Do not modify test files or reference files
