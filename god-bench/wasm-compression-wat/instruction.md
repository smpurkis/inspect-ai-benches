# Canonical QuiltPress-Q1 Payload

Edit exactly `/app/files/candidate_kernel.wat` (target: 90-150 WAT LOC).

Complete `$encode_payload` so it makes the same left-to-right token choice as `/app/files/quiltpress_q1.py` and coalesces adjacent commands canonically. Dictionary order is already canonical. At each position, use the first matching five-byte dictionary entry; otherwise emit one literal byte. Coalesce adjacent values of one kind into blocks of at most 255. Token indexes are two-byte little-endian values.

Trusted fragments provide WASI I/O, memory, dictionary construction, QPX1 headers, limits, and a validated decoder. `build_wasm.sh` concatenates the trusted prefix, your kernel, and the trusted suffix into a temporary module and atomically creates the declared `quiltpress_wasi.wasm` output.

Work offline using only WAT/WASM. Do not modify trusted files or generated output. The runner always performs the trusted build and provides no Python fallback.

Run `python3 -m pytest -q /app/files/tests.py`.
