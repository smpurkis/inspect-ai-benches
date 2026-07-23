# SamScript to WASI

Edit only `compiler.py` and `evidence.json`. Implement:

`python3 /app/files/compiler.py compile INPUT -o OUTPUT --target wasm32-wasi`

Compile SamScript into deterministic, executable WASI modules; source computation must remain reachable at runtime. The workspace contains conflicting versioned material. Follow the authority named by `contract.toml`.

Record exactly `authority`, `evidence`, and `summary` in `evidence.json`; cite every relevant path from the contract using `path:start-end` line ranges.

Use `strict_build` for the fixed toolchain smoke, then run `python3 -m pytest -q /app/files/tests.py`.
