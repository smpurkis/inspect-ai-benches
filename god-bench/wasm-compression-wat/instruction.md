# QuiltPress-Q1 in WAT/WASM

Edit exactly `/app/files/quiltpress_wasi.wat`.

Port the deterministic, lossless QuiltPress-Q1 codec specified by `/app/files/quiltpress_q1.py` to WAT for entry `/app/files/run_wasm_codec.sh`. Use `bash /app/files/run_wasm_codec.sh compress INPUT OUTPUT` and `bash /app/files/run_wasm_codec.sh decompress INPUT OUTPUT`. Preserve exact QPX1 compatibility and reject malformed streams; format and limit details are in the reference and `contract.toml`.

Compression must follow the reference's dictionary ordering and payload selection deterministically. Compression input is limited to 32 MiB, declared and produced output to 64 MiB, and each command to 120 seconds.

Work offline using only WAT/WASM. Do not modify the generated `/app/files/quiltpress_wasi.wasm`, Python reference, runner, tests, or fixtures. The runner recompiles the submitted WAT and provides no Python fallback.

Run `python3 -m pytest -q /app/files/tests.py`.
