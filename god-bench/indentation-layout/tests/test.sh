#!/bin/bash
set -u

mkdir -p /logs/verifier
score=1
bash /app/files/run_tests.sh public || score=0
bash /app/hidden/run_hidden.sh || score=0
printf '%s\n' "$score" > /logs/verifier/reward.txt
exit 0
