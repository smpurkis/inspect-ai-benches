#!/bin/bash
set -u

mkdir -p /logs/verifier
score=1
wat2wasm /app/files/lz77.wat -o /app/files/lz77.wasm || score=0
python3 -m pytest -q /app/files/tests.py || score=0
python3 -m pytest -q /app/hidden/hidden_tests.py || score=0
printf '%s\n' "$score" > /logs/verifier/reward.txt
exit 0
