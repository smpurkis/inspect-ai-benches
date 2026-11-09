# GOD-Bench Token-Efficient Redesign Progress

Branch: `god-bench-token-efficient-redesign`

Source specification: `god-bench-token-efficient-redesign.md`

## Status

- [x] Create an isolated implementation branch.
- [x] Create this progress ledger.
- [x] Implement strict budget configuration and contract loading.
- [x] Implement weighted tool policy, progress fingerprints, and usage tracing.
- [x] Implement controlled strict-mode tools and compact public-test feedback.
- [x] Replace open-ended generation with a bounded, checkpointed solver loop.
- [x] Separate public and hidden verification and redact hidden diagnostics.
- [x] Make correctness binary and attach efficiency metadata.
- [x] Add capability, budgeted-capability, and efficiency reports.
- [x] Migrate active Core-GOD tasks to compact task cards and contracts.
- [x] Convert `samscript-wasi` into the initial GOD-Context task.
- [x] Make `cifar10-burn` quiet, deterministic, and compute-bounded.
- [x] Add harness unit and integration tests.
- [x] Validate all migrated task configurations.
- [ ] Run competent-model calibration and set percentile-derived final budgets.
- [x] Run independent acceptance verification.

## Decisions

- Strict mode uses provider-billed model tokens for the token-efficiency factor.
  Tool-return characters are reported separately because they are billed again as
  later model input and must not be double-counted.
- `functional_pass` is gated by the hidden suite. Final public results remain
  diagnostic, and public-contract assertions are duplicated in hidden coverage.
- Partial public and hidden pass fractions are diagnostic metadata only.
- Strict mode does not expose unrestricted `bash` or `python`; legacy mode keeps
  the current tools during migration.
- Inspect's `message_limit`, `token_limit`, `time_limit`, and `max_tool_output`
  provide hard ceilings. Custom policy enforces weighted tool cost, read bytes,
  public-test runs, repeated actions, and finalization behavior.
- `hello-world` remains a harness smoke test and is excluded from capability
  leaderboard aggregation.

## Verification Log

- Runtime environment verified with `/home/sam/.local/bin/uv 0.9.5` and
  `inspect-ai 0.3.217`.
- Inspect supports `generate(tool_calls="single")`, task-level hard limits, and
  generation output caps.
- Common harness and reporting tests: 121 passed.
- All 10 substantive active tasks load strict contracts and instantiate.
- Active test collection: 328 tests across public and hidden suites after public
  suites were reduced to 4-8 smoke tests per task.
- Active task cards are within their Core-GOD limits; `samscript-wasi` is within
  its 140-token limit and has a 16k-token heterogeneous context corpus.
- Every active strict compose service is offline (`network_mode: none`).
- CIFAR's offline Docker image, Cargo metadata/check/release build, and repeated
  deterministic training/inference hashes were validated.
- End-to-end `mockllm` Docker smoke completed in 12 seconds. It produced binary
  failure, 252 billed tokens, complete usage metadata, sanitized feedback, and
  isolated verifier execution; no benchmark containers remained afterward.
- A second no-build `physics-2d` Docker smoke completed with eval status
  `success`, binary failure, 252 billed tokens, a 0.76-second agent trace,
  pristine-public-plus-randomized-hidden verifier gating, and no leaked
  containers.
- Leaderboard rows are ranked by pass count, under-budget pass count, summed
  solved efficiency, then solved token/tool/time medians.
- GOD-Context traces report unique files opened, relevant files opened, and
  retrieval precision from contract-declared evidence paths.
- Final independent goal verification accepted every implementation-applicable
  Section 13 criterion and found no remaining code defects. The branch is ready
  for model calibration and review.
- Current Inspect zstd `.eval` archives are parsed through `read_eval_log`, with
  the legacy ZIP parser retained for older logs.
- A real-model calibration was attempted, but the repository `.env` contains a
  placeholder Azure endpoint. The available local endpoint requires an API key
  not present in the environment. The runner now reports such eval errors rather
  than treating them as successful `n/a` attempts.
- A localhost Qwen3.6 harness check reached the model successfully but exposed
  missing descriptions on the returned strict tool functions. Inspect rejected
  the second turn before tool execution; two errored runs were retained under
  `logs/qwen36-harness-check-20260722/` and the third was cancelled. All five
  returned tools now have provider-serializable descriptions with a regression
  test.
