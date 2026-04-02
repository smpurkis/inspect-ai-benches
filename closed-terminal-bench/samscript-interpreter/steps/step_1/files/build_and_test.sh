#!/bin/bash
set -e

CONTAINER=samscript-interpreter-default-1
SRC_DIR="$(dirname "$0")/src"

# Copy files into container
docker cp "$SRC_DIR/." "$CONTAINER:/app/src/"
docker cp "$(dirname "$0")/Cargo.toml" "$CONTAINER:/app/Cargo.toml"
docker exec "$CONTAINER" mkdir -p /app/step_1/files/samples
docker cp "$(dirname "$0")/samples/." "$CONTAINER:/app/step_1/files/samples/"
docker cp "$(dirname "$0")/tests.py" "$CONTAINER:/app/step_1/files/tests.py"

# Build
echo "=== Building ==="
docker exec "$CONTAINER" bash -c 'cd /app && cargo build --release 2>&1'

# Test
echo "=== Testing ==="
docker exec "$CONTAINER" bash -c 'python3 -m pytest /app/step_1/files/tests.py -v 2>&1'
