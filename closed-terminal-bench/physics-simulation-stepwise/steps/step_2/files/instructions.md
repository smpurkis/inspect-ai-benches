# N-Body Physics Simulator — Step 2: Adaptive Timestepping

Add adaptive timestepping: when two bodies come within 10× the collision threshold,
automatically halve dt for that step and the following 3 steps.

## Requirements

Keep the --batch flag but add adaptive timestepping to the simulation:

1. Before each step, check ALL pairs for minimum approach distance (use continuous check from Step 1)
2. If any pair is within 10 × collision_threshold distance: use dt/2 for this step + next 3 steps
3. Adaptive steps count toward actual_steps but not num_steps (config value)
4. Batch summary must include `actual_steps` field alongside `num_steps`

## Batch Summary Schema (updated)

```json
{
  "seed_file": "seed_01.json",
  "initial_energy": -123.456,
  "final_energy": -123.457,
  "energy_drift": 0.001,
  "collision_count": 0,
  "final_positions": [[x, y, z], ...],
  "num_steps": 100,
  "actual_steps": 112
}
```

Where:
- `seed_file` — filename only (not full path)
- `initial_energy` — total energy at step 0
- `final_energy` — total energy at the last step
- `energy_drift` — `|final_energy - initial_energy|`
- `collision_count` — number of collision events detected
- `final_positions` — positions of all bodies at the last step
- `num_steps` — total number of simulation steps (from config)
- `actual_steps` — actual number of integration steps taken (>= num_steps when adaptive)

## Additional Requirements

- Batch results must be sorted by `seed_file` (alphabetical order).
- Each batch result must match the result of running the same seed individually.
- An empty input directory produces an empty JSON array `[]`.
- Malformed seed files produce a clear error message (not a crash/panic).
- Output must use full f64 precision (serde_json default serialization).

## Verification

    python3 -m pytest /app/step_2/files/tests.py -v

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test or verifier files.
