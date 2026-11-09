# Deterministic CIFAR-10 Training Policy

Edit only `/app/files/cifar-infer/src/training_policy.rs`. The Burn model, data loader, optimizer loop, checkpoint serialization, and policy probe are supplied. Implement four deterministic policy functions used by the trusted trainer:

- `augmentation(seed, epoch, sample_id)` returns a horizontal-flip flag and integer crop offsets in `[-4, 4]`. Form `state = seed ^ sample_id * 0x9E3779B97F4A7C15 ^ rotate_left(epoch, 32)` with wrapping `u64` arithmetic, apply the SplitMix64 finalizer implemented by the scaffold's `mix64`, then use bit 0 for `flip`, bits starting at 1 modulo 9 minus 4 for `pad_x`, and bits starting at 8 modulo 9 minus 4 for `pad_y`.
- `learning_rate(base_lr, epoch, total_epochs)` linearly warms up through `min(5, total_epochs)` epochs, reaching `base_lr` on the final warmup epoch. It then follows half-cosine decay from `base_lr` to exactly zero at `epoch == total_epochs`. Reject non-finite/non-positive rates, zero total epochs, and epochs beyond the end.
- `class_weights(counts)` returns `sum(counts) / (10 * counts[i])` for each of ten strictly positive class counts. Reject zero counts and overflow.
- `prefer_checkpoint(candidate, current)` compares validation accuracy first (higher), validation loss second (lower), and epoch last (earlier). Reject non-finite metrics. A missing current checkpoint always loses to a valid candidate.

Do not use randomness, global mutable state, filesystem state, or new dependencies. Preserve the public API and error messages are not graded. A natural solution is 70-130 changed lines.

Build with `cd /app/files/cifar-infer && cargo build --release --locked --offline`.

Run `python3 -m pytest -q /app/files/tests.py`.
