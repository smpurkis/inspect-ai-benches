# Compression Algorithm — Port to WASM/WASI in WAT

A reference Python implementation of a compression algorithm is provided at `/app/files/quiltpress_q1.py`. Port it to WebAssembly by writing WAT (WebAssembly Text Format) and compiling with `wat2wasm`. Do not use C, Rust, or Go toolchains — WAT is the only permitted source format.

## Required artifacts (you must create these)

- `/app/files/quiltpress_wasi.wat` — write from scratch by porting the Python reference
- `/app/files/quiltpress_wasi.wasm` — compile with `wat2wasm quiltpress_wasi.wat -o quiltpress_wasi.wasm`
- `/app/files/run_wasm_codec.sh` (provided — do not modify)

## Runtime contract

```
run_wasm_codec.sh compress <input> <output>
run_wasm_codec.sh decompress <input> <output>
```

## Requirements

- The runner executes the WASM implementation via wasmtime, not a Python fallback
- Study `/app/files/quiltpress_q1.py` (the Python reference), then write `quiltpress_wasi.wat` from scratch and compile it with `wat2wasm` to produce `quiltpress_wasi.wasm`
- Compress/decompress roundtrip must be byte-for-byte exact

## Self-verification

    python3 -m pytest /app/files/tests.py -v

## Constraints

- Work entirely offline
- Keep outputs deterministic
- Do not modify test files or `run_wasm_codec.sh`
- Do not use Cargo/Rust/Go/C toolchains; use `wat2wasm` only
