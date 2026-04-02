#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: run_wasm_codec.sh <compress|decompress> <input> <output>" >&2
  exit 2
fi

MODE="$1"
INPUT_FILE="$2"
OUTPUT_FILE="$3"

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
WASM_FILE="${QTP_WASM_FILE:-${SCRIPT_DIR}/quiltpress_wasi.wasm}"
WAT_FILE="${QTP_WAT_FILE:-${SCRIPT_DIR}/quiltpress_wasi.wat}"

if [[ ! -f "${WAT_FILE}" ]]; then
  echo "missing wat file: ${WAT_FILE}" >&2
  exit 1
fi

if [[ ! -f "${WASM_FILE}" ]]; then
  echo "missing wasm file: ${WASM_FILE}" >&2
  exit 1
fi

case "${MODE}" in
  compress|decompress)
    ;;
  *)
    echo "unknown mode: ${MODE}" >&2
    exit 2
    ;;
esac

TMP_WASM="$(mktemp /tmp/qtp-step2-XXXXXX.wasm)"
trap 'rm -f "${TMP_WASM}"' EXIT

wat2wasm "${WAT_FILE}" -o "${TMP_WASM}"

if ! cmp -s "${TMP_WASM}" "${WASM_FILE}"; then
  echo "provided wasm does not match wat2wasm output" >&2
  exit 1
fi

exec wasmtime run --dir / -- "${TMP_WASM}" "${MODE}" "${INPUT_FILE}" "${OUTPUT_FILE}"
