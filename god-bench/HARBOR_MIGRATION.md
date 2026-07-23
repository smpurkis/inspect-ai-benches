# Native Harbor Migration

## Scope

The ten active token-efficient GOD-Bench tasks use
`harbor-framework/harbor==0.20.0` directly. Inspect AI is not installed by the
GOD-Bench project and is not present in the active runner, agent, verifier, or
reporting path.

Archived tasks and the `hello-world` smoke fixture are not part of the native
token-efficient dataset. They remain historical fixtures until separately
migrated.

## Completed

- [x] Native Harbor `task.toml` and `instruction.md` for all ten active tasks.
- [x] No-network agent environments.
- [x] Fresh no-network verifier environments under `tests/`.
- [x] Native custom Harbor agent with bounded model turns and controlled tools.
- [x] Provider token, cache token, tool, read, retry, wall-time, and retrieval tracing.
- [x] Model-token request preflight to prevent avoidable budget overshoot.
- [x] Narrow editable artifact publication and transfer.
- [x] Native custom Harbor verifier with pristine reconstruction and hidden-test isolation.
- [x] Binary correctness gating and correctness-first efficiency rewards.
- [x] Native Harbor `result.json` reporting and leaderboard aggregation.
- [x] Harbor live output and `harbor view` workflow.

## Verification

- 54 common harness, task-manifest, verifier, tool-policy, usage, and reporting tests pass.
- Harbor 0.20 loads all ten native task manifests.
- All ten verifier Compose definitions validate.
- All ten verifier scripts pass `bash -n`.
- Native real-model runs:
  `jobs/native-smoke/qwen36-physics2d-native-smoke-7/` and
  `jobs/native-validation/qwen36-native-validation/`.
- The smoke completed one Harbor trial with no exception, used a separate verifier,
  left no task containers running, and produced complete native results.
- The final physics smoke stopped before another request could exceed its 32k
  budget: 23,180 billed tokens, 12 weighted tool cost, 15,974 read bytes, one
  attempted implementation edit, and valid usage metadata.
- Verification overlaid only `physics2d.py`; public diagnostic pass fraction was
  0.667, hidden diagnostic pass fraction was 0.216, and binary correctness was 0.
- Missing provider usage fails efficiency validation closed, editable artifact
  handoff is size-bounded, verifier-created random seeds are retained privately,
  and candidate-created processes are terminated before hidden tests are staged.
- Native `wasm-lz77` and GOD-Context `samscript-wasi` runs completed without
  Harbor exceptions. The context run recorded 7 unique files opened, 2 relevant
  files opened, and 0.286 retrieval precision, then correctly received binary
  failure from the isolated verifier.

## Pending Calibration

- Run multiple capable and weaker model baselines across all ten tasks.
- Set final task budgets from successful-run percentiles.
