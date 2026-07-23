# LZ77 in WAT/WASM

Edit exactly `/app/files/lz77.wat`.

Implement the deterministic, lossless LZ77-T1 codec in WAT for entry `/app/files/run_lz77.sh`. Use `bash /app/files/run_lz77.sh compress INPUT OUTPUT` and `bash /app/files/run_lz77.sh decompress INPUT OUTPUT`. The trusted build generates `/app/files/lz77.wasm`; the runner recompiles the submitted WAT for execution.

Follow the exact stream format and codec limits in `contract.toml`. Reject malformed streams. Identical inputs must produce identical encodings, and repetitive inputs must compress below half their original size.

Work offline using only WAT/WASM. Do not modify the generated artifact, runner, tests, or corpus. Each command is limited to 120 seconds, 8 MiB of input, and 32 MiB of output.

Run `python3 -m pytest -q /app/files/tests.py`.
