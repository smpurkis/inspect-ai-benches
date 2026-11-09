#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
TMP_WAT="$(mktemp /tmp/quiltpress-module-XXXXXX.wat)"
TMP_WASM="$(mktemp /tmp/quiltpress-module-XXXXXX.wasm)"
trap 'rm -f -- "$TMP_WAT" "$TMP_WASM"' EXIT

cat -- "$SCRIPT_DIR/trusted_prefix.wat" "$SCRIPT_DIR/candidate_kernel.wat" \
  "$SCRIPT_DIR/trusted_suffix.wat" > "$TMP_WAT"
wat2wasm "$TMP_WAT" -o "$TMP_WASM"
mv -- "$TMP_WASM" "$SCRIPT_DIR/quiltpress_wasi.wasm"
