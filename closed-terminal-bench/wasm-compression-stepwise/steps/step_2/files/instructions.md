# Compression Algorithm Step 2 (WASM/WASI port)

Precondition: complete this only after Step 1 passes.

Port the Step 1 algorithm to WASM/WASI by writing WebAssembly text format (WAT) and compiling it with `wat2wasm`. Do not use C, Rust, or Go toolchains — WAT is the only permitted source format.

## Required artifacts

- `/app/step_2/files/quiltpress_wasi.wasm`
- `/app/step_2/files/quiltpress_wasi.wat`
- `/app/step_2/files/run_wasm_codec.sh` (provided and must not be modified)

## Runtime contract

```
run_wasm_codec.sh compress <input> <output>
run_wasm_codec.sh decompress <input> <output>
```

## Requirements

- The runner must execute the wasm implementation (wasmtime, deno, or another available wasm runtime), not a Python fallback.
- Step 2 is restricted to WAT->WASM only. Provide `quiltpress_wasi.wat` and compile it with `wat2wasm` to produce `quiltpress_wasi.wasm`.

## Verification

- Tests at `/app/step_2/files/tests.py`

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_2/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify verifier files.
- Do not modify `/app/step_2/files/run_wasm_codec.sh`.
- Do not use Cargo/Rust/Go/C toolchains to build the wasm binary; use `wat2wasm` from `quiltpress_wasi.wat`.
