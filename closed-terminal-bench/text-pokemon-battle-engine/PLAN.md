# Text Pokemon Battle Engine Plan

This benchmark is a staged, text-only coding task focused on building a
deterministic Pokemon-style battle simulator and renderer. It avoids ROM and
emulator integration entirely and is intended to be automatically verifiable
with pytest using structured battle fixtures.


## Benchmark Summary

Suggested task name:

- `text-pokemon-battle-engine`

Core idea:

- The model repairs and extends a broken text battle engine over 3 steps.
- The final deliverable is a deterministic simulator, transcript generator, and
  CLI or library entrypoint that can replay battle scenarios from fixture files.
- Verification is based on structured final state, turn-by-turn snapshots, and
  canonical text output.


## Recommended 3-Step Structure

### Step 1: Core 1v1 Battle Loop

Objective:

- Repair a broken engine so it can run a simple 1v1 battle scenario end to end.

What it tests:

- state modeling
- turn order
- damage resolution
- type effectiveness
- deterministic execution
- text transcript generation

Success conditions:

- engine starts and loads scenario files
- public sample battle completes without crashing
- winner, final HP, and transcript match the reference behavior

Suggested visible checks:

- sample battle outcome
- speed-based ordering
- same-seed determinism
- transcript line formatting for a public scenario


### Step 2: Real Mechanics

Objective:

- Extend the engine to support status conditions, stat stages, switching, and
  multi-turn battle flow.

What it tests:

- effect ordering
- residual damage timing
- move legality / PP handling
- switch action handling
- edge-case correctness

Success conditions:

- visible and hidden scenarios all replay correctly
- malformed scenarios are rejected cleanly
- state snapshots match reference results turn by turn

Suggested visible checks:

- poison / burn timing
- paralysis or sleep interactions
- stat stage clamping
- switching before/after faint events


### Step 3: Deep Deterministic Engine

Objective:

- Add a higher-complexity mechanic layer while preserving deterministic replay
  and canonical text rendering.

Candidate mechanic sets:

- priority moves + abilities + held items
- weather + recoil + recovery + protect-style logic
- multi-hit moves + criticals + deterministic RNG stream

What it tests:

- complex interaction ordering
- hidden edge-case handling
- stable trace generation
- long deterministic replays

Success conditions:

- all public and hidden scenarios match reference outputs
- canonical transcript or state trace is byte-identical
- no illegal state transitions occur


## Deliverables

Typical expected files:

- `battle_engine.py` or equivalent
- `models.py`
- `renderer.py`
- `battle_cli.py`
- optional `data/` fixtures read by the engine

The candidate should not edit tests or fixture files.


## Verification Strategy With Pytest

Use scenario fixtures such as:

- `species.json`
- `moves.json`
- `type_chart.json`
- `scenario_public_01.json`
- `expected_transcript_public_01.txt`
- `expected_turn_states_public_01.json`

Example assertions:

```python
def test_step1_public_battle():
    result = run_scenario("scenario_public_01.json")
    assert result.winner == "p1"
    assert result.turn_count == 4
    assert result.final_state.p2_active.hp == 0


def test_step2_status_timing():
    result = run_scenario("scenario_poison_switch.json")
    assert result.turn_states[2]["p1"]["status"] == "poison"
    assert result.turn_states[3]["p1"]["hp"] == 41


def test_step3_trace_exact():
    result = run_scenario("scenario_priority_weather.json", trace=True)
    assert result.trace_text == expected_trace_text
```


## Why This Benchmark Is Good

- fully text-native
- deterministic and easy to replay
- no legal/ROM complications
- difficult for real reasons: effect ordering, state transitions, transcript
  determinism, and hidden interaction bugs


## Recommended Build Path

1. Start with simulator-first verification on structured state.
2. Add transcript rendering checks second.
3. Add exact trace requirements only in Step 3.


## Suggested Folder Layout For A Future Full Task

```text
text-pokemon-battle-engine/
  PLAN.md
  eval.yaml
  run.py
  compose.yaml
  environment/
    Dockerfile
  steps/
    step_1/
      files/
        instructions.md
        tests.py
        battle_engine.py
        scenarios/
      hidden/
        hidden_tests.py
        hidden_scenarios/
    step_2/
      files/
        instructions.md
        tests.py
      hidden/
        hidden_tests.py
    step_3/
      files/
        instructions.md
        tests.py
      hidden/
        hidden_tests.py
```


## Final Recommendation

This is a strong text-only benchmark candidate and likely easier to build well
than a full Pokemon-overworld agent benchmark. If only one Pokemon-flavored
text benchmark is implemented first, this is the cleaner option.
