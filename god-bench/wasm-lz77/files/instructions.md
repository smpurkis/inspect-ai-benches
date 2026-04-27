# LZ77 Compression in WAT/WASM

Implement LZ77 compression and decompression from scratch in WebAssembly Text Format (WAT), compiled to WASM with `wat2wasm`.

## LZ77 Algorithm

LZ77 uses a sliding window to find repeated sequences:
- Scan input for the longest match in the look-back window (max window: 32KB)
- Emit a literal byte if no match found, or a (offset, length) back-reference if match ≥ 3 bytes
- Decompress by copying from the output buffer at the given offset

## Required artifacts

- `/app/files/lz77.wat` — your WAT implementation
- `/app/files/lz77.wasm` — compiled with `wat2wasm lz77.wat -o lz77.wasm`
- `/app/files/run_lz77.sh` — provided runner, do not modify

## Runtime contract

```
run_lz77.sh compress <input> <output>
run_lz77.sh decompress <input> <output>
```

## WASM I/O contract

The WASM module reads from stdin and writes to stdout. The mode (`compress` or `decompress`) is passed as `argv[1]`.

## Requirements

- Compress/decompress roundtrip must be byte-for-byte exact
- Compression ratio: ≥ 50% size reduction on the provided test corpus (`/app/files/corpus/`)
- WAT only — no C, Rust, Go toolchains

## Self-verification

    python3 -m pytest /app/files/tests.py -v

## Constraints

- Work entirely offline
- Do not modify test files or `run_lz77.sh`
