# Physics Simulation Stepwise Plan

This benchmark is a staged Rust engineering task around repairing, extending,
and optimizing a deterministic physics simulator while preserving numerical
correctness.


## Benchmark Summary

Suggested task name:

- `physics-simulation-stepwise`

Core idea:

- Step 1 fixes a broken simulator so it runs and matches reference trajectories.
- Step 2 extends it to batch runs with energy and collision summaries.
- Step 3 preserves the same behavior while hitting a hard runtime improvement.


## 3-Step Structure

### Step 1: Repair Deterministic Simulation

Objective:

- Fix a broken Rust simulation that crashes or produces unstable trajectories.

What it tests:

- debugging Rust numerical code
- deterministic seeding
- stable floating-point behavior

Verification:

- simulator runs successfully
- same seed yields deterministic output
- trajectories match trusted reference within strict tolerance
- crash, nondeterminism, or tolerance breach scores zero


### Step 2: Batch Processing And Summaries

Objective:

- Process batches of seeded initial conditions and emit per-run summaries.

What it tests:

- extension of existing code without breaking physics
- exact output schema generation
- energy accounting and collision reporting

Verification:

- all batch runs complete
- summary structure is exact
- energy drift stays below threshold for all public and hidden seeds


### Step 3: Preserve Behavior, Improve Runtime

Objective:

- speed up the simulator by at least 40 percent on the benchmark set while
  preserving behavior.

What it tests:

- performance engineering
- careful optimization under correctness constraints
- hidden benchmark robustness

Verification:

- optimized outputs still match reference trajectories and summaries
- runtime meets threshold on public and hidden seeds
- miss either target and score zero


## Implementation Notes

- use deterministic seeds and fixed timestep integration
- record public and hidden reference outputs offline once
- run timing checks in a controlled environment with warm-up and repeated runs
- compare structured outputs, not just stdout text


## Final Recommendation

This is a strong benchmark if you want a clean progression from debugging to
feature work to performance optimization in a numerically sensitive Rust codebase.
