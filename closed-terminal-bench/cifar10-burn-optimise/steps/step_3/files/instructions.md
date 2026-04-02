# CIFAR-10 Step 3 (optimized Burn inference)

Precondition: complete this only after Step 2 passes.

Optimize the Burn pipeline to hit a stricter absolute CIFAR-10 target than Step 2.
You may retrain, improve the architecture, tune hyperparameters, or apply any technique —
the requirement is a deterministic Burn-based solution that reaches the Step 3 accuracy bar and still runs through `cargo run --release`.

## Required outputs in `/app/step_3/files`

- `cifar-infer/` — a Cargo project (may be copied/modified from Step 2's project)
- `optimized_public_test_preds.npy` — predictions on the public test set

## Required inference command contract

```
cargo run --release --manifest-path /app/step_3/files/cifar-infer/Cargo.toml -- \
    --input-npz <images_npz> --output-npy <preds_npy>
```

- **Tests will invoke this exact `cargo run --release` command** on both the public test set and a held-out validation set. Your Rust binary must read the `--input-npz` file, run inference, and write predictions to `--output-npy`. Python wrappers or hardcoded outputs will fail.
- Predictions must be deterministic class IDs in `[0, 9]`.
- The input npz files use the key `test_images` for the image array.

## Requirements

- **Minimum accuracy: 0.60 (60%) on both the public test set and a held-out validation set.** This is a stricter absolute target than Step 2. Success is judged against the 60% bar, not against whether a particular Step 2 artifact happened to score lower or higher on one run. You must also beat the Step 2 model's accuracy. Consider deeper or wider small CNNs (still within the 100,000 parameter budget), better regularisation, or tuned learning rates — large architectures like ResNet or ViT will not fit in 100K parameters. You may retrain in PyTorch, re-export to ONNX, convert to Burn format, and rebuild the Rust inference binary.
- Cargo.toml must declare `burn` version `0.20` as a dependency.
- Inference must run via `cargo run --release` (not Python).

## Self-verification (important!)

After building, verify your optimized Burn inference passes the tests:

    python3 -m pytest /app/step_3/files/tests.py -v

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
