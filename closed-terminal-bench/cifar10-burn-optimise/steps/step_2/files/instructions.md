# CIFAR-10 Step 2 (Burn inference in Rust)

Precondition: complete this only after Step 1 passes.

Port the Step 1 PyTorch model to Rust using the Burn deep-learning framework.
Build a Cargo project that loads the converted model weights and runs CIFAR-10 inference.

## Setup

1. `cargo init --name cifar-infer /app/step_2/files/cifar-infer`
2. Add `burn` (with an appropriate backend, e.g. `ndarray` or `candle`) to Cargo.toml.
   The container has the latest stable Rust; use the latest burn version available on crates.io.
3. Convert the Step 1 ONNX model (from `/app/step_1/files/model.onnx`) into a Burn-native
   model record (e.g. `.mpk` via `NamedMpkFileRecorder`).

## Required outputs in `/app/step_2/files`

- `cifar-infer/` — a Cargo project that compiles and runs inference
- `model.mpk` — Burn model record (or any Burn-native format; not ONNX)
- `burn_public_test_preds.npy` — predictions on the public test set

## Required inference command contract

```
cargo run --release --manifest-path /app/step_2/files/cifar-infer/Cargo.toml -- \
    --input-npz <images_npz> --output-npy <preds_npy>
```

- **Tests will invoke this exact `cargo run --release` command** on both the public test set and a held-out validation set. Your Rust binary must read the `--input-npz` file, run inference, and write predictions to `--output-npy`. Python wrappers or hardcoded outputs will fail.
- The model path may be hardcoded or configurable; tests call the command above.
- Predictions must be deterministic class IDs in `[0, 9]`.
- The input npz files use the key `test_images` for the image array.

## Requirements

- **Minimum accuracy: 0.40 (40%) on both the public test set and a held-out validation set.** Success is judged against this absolute target, not against a particular Step 1 run. Since you are porting the Step 1 model, a correct Burn implementation should preserve its accuracy while keeping inference deterministic.
- Cargo.toml must declare `burn` as a dependency (any recent version).
- Inference must run via `cargo run --release` (not Python).

## Self-verification (important!)

After building, verify your Burn inference passes the tests:

    python3 -m pytest /app/step_2/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work offline in the container.
- Keep outputs deterministic.
- Do not modify test files under `/app/step_*/files/tests.py` (they are read-only).
