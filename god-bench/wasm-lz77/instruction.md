# Canonical LZ77 Match Search

Edit exactly `/app/files/candidate_kernel.wat` (target: 70-125 WAT LOC).

Complete `$find_match`. For each input position, return the longest match of length 3..130 whose distance is in 1..min(position, 32768). For equal lengths choose the smallest distance. Overlapping matches are valid: compare source bytes using the original input positions. Return `(length << 32) | distance`, or zero when no length-3 match exists.

Trusted fragments provide WASI, I/O, limits, decoder, token emission, and the encoder loop. `build_wasm.sh` concatenates `trusted_prefix.wat`, your kernel, and `trusted_suffix.wat` into a temporary module and atomically creates the declared `lz77.wasm` build output. The runner always invokes that build first.

Work offline using only WAT/WASM. Do not modify trusted files or generated output. Each command is limited to 120 seconds, 8 MiB of input, and 32 MiB of output.

Run `python3 -m pytest -q /app/files/tests.py`.
