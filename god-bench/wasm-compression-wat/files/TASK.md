# Canonical QuiltPress-Q1 Payload

Edit exactly `/app/files/candidate_kernel.wat` (target: 90-150 WAT LOC).

Complete `$encode_payload` to select the first matching dictionary entry and coalesce adjacent literal or token values into canonical blocks of at most 255. Token indexes are two-byte little-endian values.

Trusted fragments supply WASI, I/O, memory, dictionary construction, decoder, headers, and limits. `build_wasm.sh` assembles them with the candidate into temporary WAT and atomically writes the declared `quiltpress_wasi.wasm` output.

Work offline using only WAT/WASM. Do not modify trusted files or generated output. Limits are in `contract.toml`.

Run `python3 -m pytest -q /app/files/tests.py`.
