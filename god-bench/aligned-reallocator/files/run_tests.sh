#!/bin/bash
set -euo pipefail

mode="${1:-public}"
cd /app/files
rm -f /tmp/aligned-pool
zig build-exe src/harness.zig -O ReleaseSafe -femit-bin=/tmp/aligned-pool
if [ "$mode" = public ]; then
  python3 -m pytest -q /app/files/tests.py
elif [ "$mode" = hidden ]; then
  python3 -m pytest -q /app/hidden/hidden_tests.py
else
  printf 'usage: %s public|hidden\n' "$0" >&2
  exit 2
fi
