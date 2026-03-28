# Closed Terminal Bench Difficulty Improvements

This document proposes staged, dependency-ordered upgrades for three tasks in
`closed-terminal-bench/` to reduce saturation and improve discrimination.

## Scoring Model (applies to all tasks)

- Let `N` be the number of stages.
- A task score is `k / N`, where `k` is the number of consecutively passed stages
  starting from stage 1.
- If stage `i` fails, stages `i+1..N` score 0 by definition (hard dependency chain).
- Implementation: each verifier computes stage booleans and writes a scalar to
  `/logs/verifier/reward.txt`.

---

## 1) `candle-cifar10-tiny`

Goal: evolve from single-threshold training check into end-to-end model transfer
and deployment validation.

### Proposed staged pipeline (6 stages)

1. **Candle training validity (baseline gate)**
   - Keep current checks: expected logs, exact steps, model artifact exists,
     minimum test accuracy.
   - Tighten: verify seed/hyperparameters from `/app/train_config.json` are used.

2. **Architecture-consistent export to PyTorch**
   - Export Candle weights to `/app/export/model_state_dict.pt`.
   - Validate tensor names and shapes against `/app/model_spec.json`.

3. **Candle vs PyTorch parity on calibration batch**
   - Run both models on `/app/calib_images.npy`.
   - Enforce max absolute logit difference under threshold (for example `1e-3`).

4. **PyTorch inference on unseen set**
   - Run only the exported PyTorch model on `/app/unseen_10.npz`.
   - Require exact prediction file format and thresholded accuracy.

5. **Deterministic robustness check**
   - Evaluate deterministic perturbation set (flip/crop/noise schedule provided in
     fixture file).
   - Require minimum robust accuracy or consistency threshold.

6. **Full reproducibility check**
   - Re-run full pipeline from clean state.
   - Require identical hashes for logs, exported model, and unseen predictions.

---

## 2) `wasm-compression-stepwise`

Goal: move from syntax-level repair/rewrite to complete transformation proof.

### Proposed staged pipeline (6 stages)

1. **Repair gate**
   - Generate `fixed.wasm` from `broken.wasm`.
   - Must pass `wasm-tools validate`.

2. **Behavior restoration on canonical tests**
   - `fixed.wasm` must pass all public test vectors in `/app/tests.json`.

3. **Rewrite coverage manifest generation**
   - Produce `/app/rewrite_manifest.json` listing every target-opcode occurrence
     in `fixed.wasm` (function index + instruction index).

4. **Complete rewrite application**
   - Produce `rewritten.wasm` from `fixed.wasm` using manifest/spec.
   - Verify all targeted occurrences are rewritten, with no required site skipped.

5. **Differential semantic equivalence**
   - Run hidden/randomized invocation cases on both `fixed.wasm` and
     `rewritten.wasm`.
   - Outputs must match exactly.

6. **Deterministic rebuild**
   - Re-run rewrite pipeline twice from `broken.wasm`.
   - Require byte-identical outputs (`fixed.wasm`, `rewritten.wasm`, manifest).

---

## 3) `polyglot-c-py-sharedlib-roundtrip`

Goal: extend from public vector matching to ABI robustness and compositional
correctness.

### Proposed staged pipeline (6 stages)

1. **Public spec correctness gate**
   - Build `libtransform.so`, run `solve.py`, and match `/app/spec.json` exactly.

2. **Hidden-spec generalization**
   - Validate on hidden vectors (edge lengths, entropy-heavy inputs, degenerate
     cases).

3. **Strict ABI/error semantics**
   - Enforce return-code behavior for invalid inputs/buffer constraints.
   - Verify symbol signatures and prohibit fallback cheating paths.

4. **Roundtrip extension**
   - Add reverse transform API and generate `/app/roundtrip.json`.
   - Require `reverse(transform(x)) == x` on hidden vectors.

5. **Chunked-vs-oneshot equivalence**
   - Validate deterministic chunked processing equals one-shot transform across
     hidden random chunk boundaries.

6. **Memory safety + determinism**
   - Run memory-safety checks (valgrind/asan as available).
   - Require identical output hashes across repeated runs.

---

## Implementation Notes

- Keep tasks dependency-ordered; do not award credit for later stages when an
  earlier gate fails.
- Preserve existing task themes and assets; add fixtures only where required for
  parity/unseen/robustness checks.
- Use stage-level reporting in verifier output for easier debugging while writing
  a single scalar reward for Harbor scoring.
