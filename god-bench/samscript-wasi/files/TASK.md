# SamScript structured WASI lowering

Edit only `/app/files/lowering.py`. Parsing, lexical binding resolution, type checking, WAT assembly, Wasm encoding, WASI output, integer formatting, and CLI handling are supplied. Complete lowering for expressions and statements, especially:

- lazy `&&` and `||` with exactly-once left-to-right evaluation;
- correctly targeted `break` and `continue` in nested loops;
- early `return` from any nested conditional or loop.

Emit structured WAT through the supplied `Emitter`; do not evaluate source during compilation or embed computed output. Preserve source evaluation order. The generated `_start` must reach the lowered instructions at runtime.

Compile with `python3 /app/files/compiler.py compile INPUT -o OUTPUT --target wasm32-wasi`. Run `python3 -m pytest -q /app/files/tests.py`.
