#!/bin/bash
set -euo pipefail

mode="${1:-public}"
build=/tmp/indentation-layout-build
rm -rf "$build"
mkdir -p "$build"
cp /app/files/scaffold/*.hs "$build/"
test -f /app/files/src/Layout.hs
test ! -L /app/files/src/Layout.hs
cp /app/files/src/Layout.hs "$build/Layout.hs"
ghc -Wall -Werror -O1 -outputdir "$build/obj" -i"$build" "$build/Main.hs" -o "$build/layout-harness"

if [ "$mode" = build ]; then
  exit 0
fi
python3 -m pytest -q /app/files/tests.py
