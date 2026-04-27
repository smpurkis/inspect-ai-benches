# CIFAR-10 Training and Inference in Rust with Burn

Train a CIFAR-10 classifier and run inference entirely in Rust using the Burn deep-learning framework. Both training and inference must be implemented in Rust — do not use Python for training.

## Training data

- `/app/files/cifar_tiny.npz` — training set (NumPy npz format: `train_images`, `train_labels`)
- `/app/files/cifar_public_test.npz` — public test set (visible)
- Hidden validation set used for final scoring

## Task

1. Build a Rust Cargo project using the `burn` crate at `/app/files/cifar-infer/`
2. Train a CIFAR-10 classifier using Burn
3. Save trained model weights in Burn-native format (e.g., `.mpk`)
4. Run inference on the public test set and save predictions

## Required outputs in `/app/files`

- `cifar-infer/` — Cargo project (training + inference)
- `burn_public_test_preds.npy` — predictions on the public test set

## Required inference command contract

```
cargo run --release --manifest-path /app/files/cifar-infer/Cargo.toml -- \
    --input-npz <images_npz> --output-npy <preds_npy>
```

- Predictions must be deterministic class IDs in `[0, 9]`
- Input npz files use key `test_images`

## Requirements

- **Minimum accuracy: 0.60 (60%)** on both public test set and held-out validation set
- `burn` must be a Cargo.toml dependency
- Training and inference must be in Rust (not Python)

## Tips

- If your model falls short of 60%, iterate on the architecture — try adding more convolutional layers, batch normalisation, data augmentation, or a wider channel count.

## Self-verification

    python3 -m pytest /app/files/tests.py -v

## Constraints

- Work offline in the container
- Keep outputs deterministic
- Do not modify test files
