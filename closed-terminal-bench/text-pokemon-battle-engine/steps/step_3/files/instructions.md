# Step 3: Advanced Mechanics and Trace Mode

Extend the battle engine with priority moves, weather, multi-hit moves, critical hits, and a canonical trace output mode.

## Priority Moves

Multiple priority levels exist (see `priority` field in moves.json):
- Priority 2: Extreme Speed
- Priority 1: Quick Attack, Mach Punch
- Priority 0: Most moves
- Negative priorities are also possible

Within the same priority bracket, the faster Pokemon moves first. Different priority brackets are resolved before speed comparison.

## Weather

Support two weather conditions: **sun** and **rain**.

| Weather | Effect |
|---------|--------|
| **sun** | Fire-type moves deal 1.5x damage; Water-type moves deal 0.5x damage |
| **rain** | Water-type moves deal 1.5x damage; Fire-type moves deal 0.5x damage |

- Weather is set by moves like Sunny Day and Rain Dance (see `effect.type == "weather"` in moves.json)
- Weather lasts exactly N turns (from `effect.turns`, typically 5), counting from the turn it was set
- Weather expires at the end of the Nth turn (e.g., set on turn 1 with 5 turns → active turns 1-5, expires end of turn 5)
- The weather multiplier is applied as an additional factor in the damage formula:
  `damage = floor(base * STAB * type_effectiveness * weather_modifier * random_factor)`

## Multi-Hit Moves

Moves with `effect.type == "multi_hit"` hit 2-5 times:
- Number of hits is determined by the RNG: `rng.randint(min_hits, max_hits)`
- Each hit calculates damage independently (separate random factors)
- If the target faints mid-hit, remaining hits do not occur
- The turn result should report total damage dealt and number of hits

## Critical Hits

Implement deterministic critical hits based on the RNG:
- Critical hit chance: 1/16 per attack
- Check: `rng.randint(1, 16) == 1` (before the random factor roll)
- Critical hit multiplier: 1.5x (applied to the final damage)
- Critical hits ignore the defender's positive stat stage modifiers (stages > 0 are treated as 0)
- Critical hits do NOT ignore the attacker's negative stat stages

## Trace Mode

Add a `--trace` CLI flag and a `trace=True` parameter to `run_battle()`.

When trace mode is enabled, the engine produces a line-by-line text log in addition to the JSON output. Each trace line follows this exact format:

```
TURN {n}
  {Pokemon} used {Move}!
  {Move} deals {damage} damage to {Target} ({type}{, STAB}{, super effective|not very effective|immune}{, boosted by sun|weakened by sun|boosted by rain|weakened by rain}{, critical hit})
  {Target} HP: {current_hp}/{max_hp}
  {Pokemon} is hurt by poison! (-{dmg} HP)
  {Pokemon} fainted!
  Weather: {condition} ({turns} turns remaining)
  {Pokemon} switched in!
```

- One TURN header per turn
- Each action is indented with 2 spaces
- Damage description includes type, STAB, effectiveness, weather, and crit annotations as applicable
- Status damage is reported after attacks
- Weather status is reported if active
- Trace output is returned as a `"trace"` key in the result dict (list of strings, one per line)

The trace from `run_battle(scenario, trace=True)` must be deterministic and byte-identical across runs with the same seed.

## Key Files

- `/app/step_3/files/data/scenario_priority.json` — Priority move scenario
- `/app/step_3/files/data/scenario_weather.json` — Weather scenario
- `/app/step_3/files/data/expected_trace_01.txt` — Example trace format (template with `{dmg}` placeholders)

## Verification

```bash
python3 -m pytest /app/step_3/files/tests.py -v
```

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
- Extend `battle_engine.py` as needed.
