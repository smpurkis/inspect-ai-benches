# CIFAR-10 with Burn

Edit exactly:

- `/app/files/cifar-infer/src/model.rs`
- `/app/files/cifar-infer/src/train.rs`
- `/app/files/cifar-infer/training.toml`

Complete the Rust project entered by `/app/files/cifar-infer/Cargo.toml`. Using Burn 0.20's CPU ndarray backend, train only on `/app/files/cifar_tiny.npz` and write `/app/files/cifar-infer/model.mpk`. The inference CLI is `/app/files/cifar-infer/target/release/cifar-infer --input-npz <images.npz> --output-npy <predictions.npy>`; it must accept NCHW float32 `test_images` and emit a one-dimensional `uint8` array of class IDs 0-9. The trusted build also writes `/app/files/burn_public_test_preds.npy`.

Public, hidden, and perturbed-hidden accuracy must each be at least 60%. Training and inference must be deterministic. Work offline in Rust/Burn only: no Python, subprocesses, build scripts, pretrained artifacts, or delegated runtimes. Training is limited to 1,200 seconds, inference to 120 seconds, logs to 4,096 bytes per command, the model to 100 MB, and public predictions to 4,096 bytes. Exact commands and constraints are in `contract.toml`.

Run `python3 -m pytest -q /app/files/tests.py`.
