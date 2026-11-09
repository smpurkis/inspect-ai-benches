# Deterministic CIFAR-10 Training Policy

Edit only `cifar-infer/src/training_policy.rs`. Implement deterministic augmentation, warmup plus cosine learning-rate scheduling, inverse-frequency class balancing, and lexicographic checkpoint selection. The exact formulas, validation requirements, and test command are in the top-level task instruction supplied by Harbor.

Run `python3 -m pytest -q /app/files/tests.py`.
