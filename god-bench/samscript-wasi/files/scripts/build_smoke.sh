#!/bin/sh
# Trusted fixed-input build path. Agent-controlled arguments are intentionally absent.
set -eu

work=/tmp/samscript-strict-build
log="$work/tool.log"
rm -rf "$work"
mkdir -p "$work"

fail() {
    status=${1:-1}
    trap - HUP INT TERM
    printf '%s\n' "trusted smoke failed; capped tool output follows" >&2
    if [ -f "$log" ]; then
        dd if="$log" bs=8192 count=1 2>/dev/null >&2
    fi
    exit "$status"
}
trap fail HUP INT TERM

if ! wat2wasm /app/files/scripts/smoke_probe.wat -o "$work/probe.wasm" >"$log" 2>&1; then
    fail 1
fi
if ! wasm-objdump -x "$work/probe.wasm" >"$log" 2>&1; then
    fail 1
fi
if ! wasmtime "$work/probe.wasm" >"$work/probe.out" 2>"$log"; then
    fail 1
fi

if ! python3 /app/files/compiler.py compile /app/files/samples/arithmetic.sam \
    -o "$work/arithmetic.wasm" --target wasm32-wasi >"$log" 2>&1; then
    fail 1
fi
if ! wasm-objdump -x "$work/arithmetic.wasm" >"$log" 2>&1; then
    fail 1
fi
if ! wasmtime "$work/arithmetic.wasm" >"$work/arithmetic.out" 2>"$log"; then
    fail 1
fi
if ! grep -Fqx '10 ** 3 = 1000' "$work/arithmetic.out"; then
    printf '%s\n' "compiled smoke output mismatch" >"$log"
    fail 1
fi

printf '%s\n' "trusted WASI smoke passed"
