#!/usr/bin/env bash
# LZ77 WASM runner - do not modify this file.
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

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
WAT="${SCRIPT_DIR}/lz77.wat"
MAX_INPUT_BYTES=$((8 * 1024 * 1024))
MAX_OUTPUT_KIB=$((32 * 1024))

case "$MODE" in
    compress|decompress) ;;
    *)
        echo "unknown mode: $MODE" >&2
        exit 2
        ;;
esac

if [ ! -f "$WAT" ]; then
    echo "missing WAT source: $WAT" >&2
    exit 1
fi

if [ ! -f "$INPUT" ]; then
    echo "missing input file: $INPUT" >&2
    exit 1
fi

INPUT_SIZE="$(stat -c %s -- "$INPUT")"
if (( INPUT_SIZE > MAX_INPUT_BYTES )); then
    echo "input exceeds 8 MiB limit" >&2
    exit 1
fi

TMP_WASM="$(mktemp /tmp/lz77-XXXXXX.wasm)"
OUTPUT_DIR="$(dirname -- "$OUTPUT")"
TMP_OUTPUT="$(mktemp "${OUTPUT_DIR}/.lz77-output-XXXXXX")"
trap 'rm -f -- "$TMP_WASM" "$TMP_OUTPUT"' EXIT

wat2wasm "$WAT" -o "$TMP_WASM"

(
    ulimit -f "$MAX_OUTPUT_KIB"
    exec timeout --signal=KILL 120s wasmtime run "$TMP_WASM" -- "$MODE" < "$INPUT" > "$TMP_OUTPUT"
)

mv -- "$TMP_OUTPUT" "$OUTPUT"
