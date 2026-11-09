#!/bin/bash
set -euo pipefail

mode="${1:-public}"
build=/tmp/async-cache-generation-build
rm -rf "$build"
mkdir -p "$build/src/cache" "$build/classes"
cp /app/files/scaffold/cache/*.java "$build/src/cache/"
test -f /app/files/src/main/java/VersionedCache.java
test ! -L /app/files/src/main/java/VersionedCache.java
cp /app/files/src/main/java/VersionedCache.java "$build/src/cache/VersionedCache.java"
javac -Xlint:all -Werror -d "$build/classes" "$build"/src/cache/*.java

if [ "$mode" = build ]; then
  exit 0
fi
java -ea -cp "$build/classes" cache.PublicTests
