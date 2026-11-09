#!/bin/bash
set -u

mkdir -p /logs/verifier
score=1
cp /opt/cifar-infer-Cargo.lock /app/files/cifar-infer/Cargo.lock && CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=/app/files/cifar-infer/target cargo build --quiet --release --locked --offline --manifest-path /app/files/cifar-infer/Cargo.toml || score=0
python3 -m pytest -q /app/files/tests.py || score=0
python3 -m pytest -q /app/hidden/hidden_tests.py || score=0
printf '%s\n' "$score" > /logs/verifier/reward.txt
exit 0
