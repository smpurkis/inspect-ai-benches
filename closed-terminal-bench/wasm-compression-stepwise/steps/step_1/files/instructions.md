# Compression Algorithm Step 1 (Python bug fixing)

Fix the broken Python compressor at `/app/step_1/files/quiltpress_q1.py`.

## Requirements

- Fix the Python implementation so it runs.
- Ensure compress/decompress roundtrip is byte-for-byte exact.
- Ensure it actually compresses benchmark fixtures (`compressed_size < original_size`).
- Keep the custom format/approach; do not swap to a standard library compressor implementation.

## Verification

- Tests at `/app/step_1/files/tests.py`

## Cross-codec compatibility (critical!)

Your implementation must be **binary-compatible with the reference codec** — not just internally consistent. A common failure mode is implementing encode/decode operations that are inverses of each other *within your own implementation*, but produce output the reference codec cannot read (and vice versa).

Before assuming your roundtrip works, verify cross-codec compatibility explicitly:

1. **Check every data transformation is a true inverse.** If any step rotates, shifts, or reorders bytes (e.g. `chunk[1:] + chunk[:1]`), confirm the decode path reverses it exactly — not merely "undoes the same operation". A rotation bug can make your codec self-consistent but incompatible with any other implementation.
2. **Check your dictionary construction** produces entries that match the reference. The dictionary must be built by sliding a window over the input to find the most frequent substrings — not by sampling at aligned boundaries.
3. **Cross-codec round-trip test:** compress with your codec, decompress with the reference; then compress with the reference, decompress with yours. Both must succeed and produce the original data.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

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
- For Step 2, do not use Cargo/Rust/Go/C toolchains to build the wasm binary; use `wat2wasm` from `quiltpress_wasi.wat`.
- You may add helper source/build scripts under `/app/step_2/files` and `/app/step_3/files`.
