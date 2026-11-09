#!/bin/bash
set -euo pipefail

build=/tmp/async-cache-generation-build
cp /app/hidden/HiddenTests.java "$build/src/cache/HiddenTests.java"
javac -Xlint:all -Werror -cp "$build/classes" -d "$build/classes" "$build/src/cache/HiddenTests.java"
java -ea -cp "$build/classes" cache.HiddenTests
