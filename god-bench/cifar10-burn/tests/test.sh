#!/bin/bash
set -u

mkdir -p /logs/verifier
score=1
cp /opt/cifar-infer-Cargo.lock /app/files/cifar-infer/Cargo.lock && CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=/app/files/cifar-infer/target RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8 cargo build --quiet --release --locked --offline --manifest-path /app/files/cifar-infer/Cargo.toml && CARGO_NET_OFFLINE=true RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8 timeout --signal=KILL 1200s /app/files/cifar-infer/target/release/cifar-train --train-npz /app/files/cifar_tiny.npz --config /app/files/cifar-infer/training.toml --model-out /app/files/cifar-infer/model.mpk && CARGO_NET_OFFLINE=true RAYON_NUM_THREADS=8 OMP_NUM_THREADS=8 timeout --signal=KILL 120s /app/files/cifar-infer/target/release/cifar-infer --input-npz /app/files/cifar_public_test.npz --output-npy /app/files/burn_public_test_preds.npy || score=0
python3 -m pytest -q /app/files/tests.py || score=0
python3 -m pytest -q /app/hidden/hidden_tests.py || score=0
printf '%s\n' "$score" > /logs/verifier/reward.txt
exit 0
