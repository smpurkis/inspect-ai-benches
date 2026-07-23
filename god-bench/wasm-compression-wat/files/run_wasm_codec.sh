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
MAX_COMPRESS_INPUT=$((32 * 1024 * 1024))
MAX_ENCODED_INPUT=$((64 * 1024 * 1024))
MAX_OUTPUT_KIB=$((64 * 1024))

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

TMP_WASM="$(mktemp /tmp/qtp-step2-XXXXXX.wasm)"
SANDBOX="$(mktemp -d /tmp/qtp-wasi-XXXXXX)"
mkdir "${SANDBOX}/input" "${SANDBOX}/output"
trap 'rm -f "${TMP_WASM}"; rm -rf "${SANDBOX}"' EXIT

wat2wasm "${WAT_FILE}" -o "${TMP_WASM}"

if ! cmp -s "${TMP_WASM}" "${WASM_FILE}"; then
  echo "provided wasm does not match wat2wasm output" >&2
  exit 1
fi

cp -- "${INPUT_FILE}" "${SANDBOX}/input/data"

(
  ulimit -f "${MAX_OUTPUT_KIB}"
  exec timeout --signal=KILL 120s wasmtime run \
    --dir "${SANDBOX}/input::/input" \
    --dir "${SANDBOX}/output::/output" \
    -- "${TMP_WASM}" "${MODE}" /input/data /output/data
)

if [[ ! -f "${SANDBOX}/output/data" ]]; then
  echo "WASM codec produced no output" >&2
  exit 1
fi
cp -- "${SANDBOX}/output/data" "${OUTPUT_FILE}"
