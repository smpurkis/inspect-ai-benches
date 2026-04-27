#!/usr/bin/env bash
# LZ77 WASM runner — do not modify this file.
# Usage:
#   run_lz77.sh compress   <input_file> <output_file>
#   run_lz77.sh decompress <input_file> <output_file>
#
# The WASM module reads binary data from stdin and writes to stdout.
# The first argument (compress/decompress) is passed as argv[1].

set -euo pipefail

MODE="${1:?usage: run_lz77.sh compress|decompress <input> <output>}"
INPUT="${2:?missing input file}"
OUTPUT="${3:?missing output file}"

WASM="/app/files/lz77.wasm"

if [ ! -f "$WASM" ]; then
    echo "ERROR: $WASM not found — compile with: wat2wasm lz77.wat -o lz77.wasm" >&2
    exit 1
fi

wasmtime run --allow-precompiled "$WASM" -- "$MODE" < "$INPUT" > "$OUTPUT"
