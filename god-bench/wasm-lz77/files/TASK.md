# Canonical LZ77 Match Search

Edit exactly `/app/files/candidate_kernel.wat` (target: 70-125 WAT LOC).

Complete `$find_match`. Return the longest length up to 130 in the preceding 32 KiB, choosing the smallest distance on ties. Return `(length << 32) | distance`, or zero below length three.

Trusted fragments supply WASI, I/O, limits, decoder, emitters, and the encoder loop. `build_wasm.sh` assembles them with the candidate into temporary WAT and atomically writes the declared `lz77.wasm` output.

Work offline using only WAT/WASM. Do not modify trusted files or generated output. Limits are in `contract.toml`.

Run `python3 -m pytest -q /app/files/tests.py`.
