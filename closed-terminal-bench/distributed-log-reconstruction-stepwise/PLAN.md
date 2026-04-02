# Distributed Log Reconstruction Stepwise Plan

This benchmark is a staged data-recovery and analytics task built around
reconstructing a canonical event stream from corrupted distributed log shards,
then computing deterministic analytics from the repaired stream.


## Benchmark Summary

Suggested task name:

- `distributed-log-reconstruction-stepwise`

Core idea:

- Step 1 reconstructs the canonical stream from damaged shards.
- Step 2 builds a Rust analytics CLI over the reconstructed stream.
- Step 3 exports a stable artifact and proves determinism by re-running the
  pipeline.


## 3-Step Structure

### Step 1: Reconstruct Canonical Stream

Objective:

- Merge partially corrupted log shards containing skewed timestamps, dropped
  lines, and duplicate sequence numbers into one canonical event stream.

What it tests:

- log recovery heuristics
- ordering rules
- duplicate handling
- deterministic merge logic

Verification:

- merged log is strictly ordered
- recovered events match the reference subset exactly
- missing or duplicated events score zero


### Step 2: Build Analytics CLI

Objective:

- Build a Rust CLI that consumes the canonical stream and computes session
  counts, latency percentiles, and error classifications.

What it tests:

- Rust CLI implementation
- exact numeric reporting
- malformed input handling

Verification:

- visible and hidden analytics results match exactly
- malformed input is rejected with the correct error behavior


### Step 3: Stable Export And Determinism Pass

Objective:

- Add an export mode for a machine-readable artifact and rerun the pipeline to
  confirm determinism.

What it tests:

- stable serialization
- deterministic analytics
- end-to-end reproducibility

Verification:

- exported artifact is byte-identical across runs
- second pass reproduces the same metrics
- any nondeterministic field or format change scores zero


## Implementation Notes

- define strict canonical ordering rules in visible instructions
- expose a public subset of corrupted shards and keep hidden shards structurally
  similar rather than changing the task definition
- use stable timestamp / numeric formatting in exported artifacts


## Final Recommendation

This is a strong benchmark because it combines recovery, analytics, and
deterministic export without needing external services or arbitrary creativity.
