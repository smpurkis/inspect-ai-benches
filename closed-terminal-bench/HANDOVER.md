## Goal

Fix a critical hidden-data leakage bug in `candle-cifar10-tiny` so the LLM agent cannot access hidden files/tests, while keeping hidden evaluation executed by verifier via a fixed inference command contract.
Then rerun with GPT-5 and iterate until no leak remains.

---

## Instructions

- User explicitly requested:
  - Hidden files should **never** be accessible to the LLM agent.
  - Hidden tests should run inference themselves via a known command contract.
  - Rerun and debug in a loop until confident there is no leak.
- Keep staged 3-step behavior and staged scoring metadata.
- Continue using `uv run inspect eval ...` with GPT-5.

---

## Discoveries

- Prior 1.0 score was exploit-driven (label leakage), not real performance:
  - Agent-generated infer scripts read labels directly from input (`test_labels`) or path-derived hidden labels.
- In this framework, `files:` in `eval.yaml` are mounted into sandbox before agent run, therefore agent-visible.
- Even after removing hidden datasets from `files:`, verifier internals can still leak hidden paths if verifier is mounted in visible tree and readable by agent.
- `state.metadata` in scorer did not reliably include eval metadata at runtime for injection logic; sample metadata had values, but scorer path resolution initially failed.
- Hidden injection path fallback needed using `eval_name` + repo-relative path when `eval_file_path` unavailable in scorer context.
- Current post-fix runs consistently fail at hidden Step 1 (good sign exploit is broken):
  - Hidden test fails because infer expects `test_labels` in hidden images NPZ (not present), indicating hidden labels are no longer trivially reachable via old exploit.

---

## Accomplished

### Completed

1. **Threshold changes requested by user**
   - Set min acc to:
     - Step 1: `0.65` (visible + hidden)
     - Step 2: `0.65` (visible + hidden)
     - Step 3: `0.70` (visible + hidden)
   - Updated in tests + prompt text (`eval.yaml`, `step_instructions.json`).

2. **Removed AI-5 strict gate**
   - Removed AI-5 exact correctness checks and related references/mappings in candle task.
   - Hidden evaluation now based on held-out validation accuracy only.

3. **Initial leak analysis + confirmation**
   - Confirmed GPT-5 achieved perfect score via leakage.
   - Identified exploit path from logs: infer scripts reading labels directly.

4. **Implemented hidden-file injection support in shared scorer**
   - Added generalized hidden injection/cleanup support in `staged_eval_common.py`:
     - reads `metadata.hidden_file_injections`
     - injects files right before verifier
     - optional chmod mode support
     - cleans up after verifier
   - Added robust metadata merge helper `_state_metadata(...)`.
   - Added eval-dir resolution fallback (`eval_file_path` or `closed-terminal-bench/<eval_name>/eval.yaml`).

5. **Changed candle eval mapping to avoid pre-mounting hidden assets**
   - Removed hidden datasets and hidden tests from `files:` in candle `eval.yaml`.
   - Added `metadata.hidden_file_injections` for:
     - hidden tests
     - hidden val images/labels
   - Hidden files now injected at scoring time only.

6. **Moved hidden tests to temp hidden path and updated verifier references**
   - Verifier now points to hidden tests in `/var/tmp/.candle_hidden/...` instead of `/app/step_*/hidden/...`.

7. **Hardened hidden tests execution context**
   - Hidden tests now run infer command as user `nobody` (via `su`) to reduce privilege-based file snooping.
   - Added explicit file permission setup helper calls in hidden tests for model/infer/input and output dir.
   - Hidden tests consume hidden files from `/var/tmp/.candle_hidden/hidden_eval_{images,labels}.*`.

8. **Removed visible-test dependency on hidden paths**
   - Step 2 visible tests no longer check hidden image hash.
   - Step 3 visible tests no longer check hidden image hash (final patch applied near end).

9. **Validation runs**
   - Multiple candle-only GPT-5 reruns were executed after each fix.
   - Current behavior: score `0.0`, stage1 hidden fails (expected under current hardening; exploit path blocked).
   - Latest logs confirm no `/app/step_1/hidden/hidden_tests.py` visibility in messages, but verifier temp hidden test path still appears in failure text (`/var/tmp/.candle_hidden/step_1_hidden_tests.py`).

### In progress / still to do

- **Main remaining leak surface**: agent can still read verifier script:
  - `step_3/hidden/verifier.py` is mounted under `/app/step_3/hidden/verifier.py` (visible to agent), and contains hidden test temp paths.
- Need to **hide verifier itself** from agent phase (likely via same hidden injection mechanism):
  - Remove verifier mapping from `files:`.
  - Inject verifier at scoring time via `hidden_file_injections`.
  - Update `verifier_command` to point to hidden-injected verifier path (or keep path but only inject at score time).
- Ensure hidden test failure details/path don't leak sensitive structure to future turns (optional but desirable).
- Rerun loop after verifier-hiding change; inspect logs for:
  - no hidden paths discoverable during agent phase,
  - no hidden labels path leakage,
  - stage behavior still valid.

---

## Relevant files / directories

### Shared scorer logic (core leak-fix mechanism)
- **Edited:** `staged_eval_common.py`
  - Added:
    - `_state_metadata(...)`
    - `_resolve_hidden_file_injections(...)`
    - `_resolve_eval_dir_for_injections(...)`
    - `_inject_hidden_files(...)`
    - `_cleanup_injected_hidden_files(...)`
  - `staged_reward_scorer` now uses merged metadata + injection lifecycle.

### Candle eval wiring
- **Edited:** `closed-terminal-bench/candle-cifar10-tiny/eval.yaml`
  - Removed hidden files from static `files:`.
  - Added `metadata.hidden_file_injections` entries.
  - Threshold text updates (0.65/0.65/0.70).
  - Still currently maps verifier in visible `files:` (remaining issue).

### Candle verifier
- **Edited:** `closed-terminal-bench/candle-cifar10-tiny/steps/step_3/hidden/verifier.py`
  - Hidden test paths changed from `/app/step_*/hidden/hidden_tests.py` to `/var/tmp/.candle_hidden/step_*_hidden_tests.py`.
  - Verifier itself still visible via `/app/step_3/hidden/verifier.py` mapping.

### Candle hidden tests
- **Edited:**
  - `closed-terminal-bench/candle-cifar10-tiny/steps/step_1/hidden/hidden_tests.py`
  - `closed-terminal-bench/candle-cifar10-tiny/steps/step_2/hidden/hidden_tests.py`
  - `closed-terminal-bench/candle-cifar10-tiny/steps/step_3/hidden/hidden_tests.py`
- Changes:
  - Use hidden data from `/var/tmp/.candle_hidden/hidden_eval_images.npz` and `hidden_eval_labels.npy`.
  - Run infer via `su ... nobody`.
  - Added permission helper functions for execution/read/write setup.
  - Threshold constants updated.

### Candle visible tests
- **Edited:**
  - `closed-terminal-bench/candle-cifar10-tiny/steps/step_1/files/tests.py` (threshold update)
  - `closed-terminal-bench/candle-cifar10-tiny/steps/step_2/files/tests.py` (threshold update + removed hidden hash check)
  - `closed-terminal-bench/candle-cifar10-tiny/steps/step_3/files/tests.py` (threshold update + removed hidden hash check)

### Step instructions text
- **Edited:** `closed-terminal-bench/candle-cifar10-tiny/step_instructions.json`
  - Updated thresholds and removed AI-5 mention.

### Runner used
- `candle_cifar10_tiny_only.py`

### Useful recent eval logs
- `logs/2026-03-20T08-46-39+00-00_candle-cifar10-tiny-only_ENAaky84ExWHnXkckpvLFn.eval`
- `logs/2026-03-20T08-54-10+00-00_candle-cifar10-tiny-only_6n5ivTYXWETfWEsNBMv8Sf.eval`
- `logs/2026-03-20T09-01-05+00-00_candle-cifar10-tiny-only_b8FE4BqA9Ti4y9hU3tNGrC.eval`
- Earlier exploit-success run for reference:
  - `logs/2026-03-20T01-41-32+00-00_candle-cifar10-tiny-only_PBYoGknBmvyqhrfWVzDLWJ.eval`
