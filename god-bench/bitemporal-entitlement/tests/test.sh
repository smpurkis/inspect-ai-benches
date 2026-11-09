#!/bin/bash
set -u

mkdir -p /logs/verifier
score=1
bash /app/files/run_tests.sh public || score=0
bash /app/files/run_tests.sh hidden || score=0
printf '%s\n' "$score" > /logs/verifier/reward.txt
exit 0
