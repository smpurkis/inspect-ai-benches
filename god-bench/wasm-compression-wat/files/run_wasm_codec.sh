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
WASM_FILE="${SCRIPT_DIR}/quiltpress_wasi.wasm"
BUILD_FILE="${SCRIPT_DIR}/build_wasm.sh"
MAX_COMPRESS_INPUT=$((32 * 1024 * 1024))
MAX_ENCODED_INPUT=$((64 * 1024 * 1024))
MAX_OUTPUT_KIB=$((64 * 1024))

if [[ ! -f "${SCRIPT_DIR}/candidate_kernel.wat" ]]; then
  echo "missing candidate kernel" >&2
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

if [[ ! -f "${INPUT_FILE}" ]]; then
  echo "missing input file: ${INPUT_FILE}" >&2
  exit 1
fi

INPUT_SIZE="$(stat -c %s -- "${INPUT_FILE}")"
if [[ "${MODE}" == "compress" && ${INPUT_SIZE} -gt ${MAX_COMPRESS_INPUT} ]]; then
  echo "compression input exceeds 32 MiB limit" >&2
  exit 1
fi
if [[ "${MODE}" == "decompress" && ${INPUT_SIZE} -gt ${MAX_ENCODED_INPUT} ]]; then
  echo "compressed input exceeds 64 MiB limit" >&2
  exit 1
fi

OUTPUT_DIR="$(dirname -- "${OUTPUT_FILE}")"
TMP_OUTPUT="$(mktemp "${OUTPUT_DIR}/.quiltpress-output-XXXXXX")"
trap 'rm -f -- "${TMP_OUTPUT}"' EXIT
bash "${BUILD_FILE}"

(
  ulimit -f "${MAX_OUTPUT_KIB}"
  exec timeout --signal=KILL 120s wasmtime run \
    "${WASM_FILE}" -- "${MODE}" < "${INPUT_FILE}" > "${TMP_OUTPUT}"
)

mv -- "${TMP_OUTPUT}" "${OUTPUT_FILE}"
