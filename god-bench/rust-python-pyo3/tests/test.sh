#!/bin/bash
set -u

mkdir -p /logs/verifier
score=1
cp /app/files/src/lib.rs /app/src/lib.rs && (cd /app && maturin develop --release) || score=0
python3 -m pytest -q /app/files/tests.py || score=0
python3 -m pytest -q /app/hidden/hidden_tests.py || score=0
printf '%s\n' "$score" > /logs/verifier/reward.txt
exit 0
