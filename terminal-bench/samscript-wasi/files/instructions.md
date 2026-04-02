# SamScript WASM Compiler

Write a compiler that compiles SamScript programs to WebAssembly (WASM/WASI) binaries that run under `wasmtime`.

## Goal

Create a compiler invocable as:

```bash
samscript compile <input.sam> -o <output.wasm> --target wasm32-wasi
wasmtime output.wasm
```

The compiler binary must be at `/app/samscript` or `/app/target/release/samscript`.

## Language specification

See `/app/files/language_spec.md` for the complete SamScript language spec. Your compiler must support:

- `print(value)` — print to stdout with newline
- String literals (`"hello"`), interpolation (`"${expr}"`), concatenation (`..` operator)
- Number literals — all numbers are f64
- Number formatting: integers print without decimal point (e.g., `10.0` → `"10"`)
- Arithmetic: `+`, `-`, `*`, `/`, `%`, `**` (exponentiation)
- Unary negation (`-x`)
- Variables: `let` (mutable), `const` (immutable)
- Compound assignment: `+=`, `-=`, `*=`, `/=`, `%=`
- Functions with parameters and return values
- `if`/`else if`/`else` conditionals
- `loop`/`break`/`continue`
- Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Logical: `and`, `or`, `not`
- Booleans: `true`, `false`
- Built-in functions: `str()`, `len()`, `type()`, `num()`
- Division by zero → runtime error (exit code 1)

## WASM/WASI requirements

See `/app/files/wasi_spec.md` for details. Key points:

- Valid WASI preview1 module
- Import `fd_write` from `wasi_snapshot_preview1` for stdout
- Import `proc_exit` for exit codes
- Export `memory` and `_start`
- Exit code 0 on success, 1 on runtime error
- Output must be **deterministic**: compiling the same source twice must produce byte-identical `.wasm` files

## Available tools

- **Rust toolchain** (1.85.0) with `wasm32-wasip1` target pre-installed
- **Cranelift** code generation libraries pre-vendored (see `/app/Cargo.toml`)
- **wabt** installed — includes `wat2wasm` for converting WAT text format to `.wasm` binary
- **wasmtime** installed for running `.wasm` binaries

### Approach 1: Rust compiler with cranelift

A Rust project skeleton is at `/app/` with cranelift dependencies pre-vendored for offline builds:

```
/app/Cargo.toml          — cranelift-codegen, cranelift-frontend, cranelift-module, cranelift-object
/app/vendor/             — pre-vendored crates
/app/.cargo/config.toml  — offline build config
/app/src/main.rs         — stub (replace with your compiler)
```

Write your compiler in `src/main.rs` and build:

```bash
cargo build --release
# Binary at /app/target/release/samscript
```

Dependencies are pre-compiled — only your code needs to build.

### Approach 2: Generate WAT and convert

Write a compiler (in Python, Rust, or any language) that generates WAT (WebAssembly Text format), then convert:

```bash
wat2wasm output.wat -o output.wasm
```

If using Python, create `/app/samscript` as an executable script with `#!/usr/bin/env python3`.

### Approach 3: Transpile to Rust, compile to WASM

Write a transpiler that converts SamScript to Rust source code, then compile with:

```bash
rustc --target wasm32-wasip1 -o output.wasm generated.rs
```

Any approach that produces the correct CLI interface and working WASM output is acceptable.

## Sample programs

Example programs in `/app/files/samples/`:

- `hello.sam` — prints "hello world"
- `arithmetic.sam` — arithmetic with string interpolation
- `functions_loops.sam` — factorial, fibonacci, function calls and loops
- `string_ops.sam` — string concatenation, `str()` builtin, loop-based string building
- `logic.sam` — boolean operations, comparisons, if/else chains

Test your compiler:

```bash
samscript compile /app/files/samples/hello.sam -o /tmp/test.wasm --target wasm32-wasi
wasmtime /tmp/test.wasm
# Should print: hello world
```

## Self-verification

Run the visible tests:

```bash
python3 -m pytest /app/files/tests.py -v
```

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing. If any test fails, fix your compiler and rebuild.

## Important: no shortcuts

The compiled `.wasm` binaries are **structurally analyzed**. The WASM must contain real compiled code — actual arithmetic instructions, control flow, and function calls that correspond to the source program.

Shortcuts like "eval-and-embed" — where you interpret the source program at compile time, capture its output, and embed the output string in a minimal WASM wrapper that just prints it — **will be detected and penalized**. The hidden tests inspect the WASM binary to verify that computation happens at runtime, not at compile time.

Your compiler must translate SamScript language constructs into corresponding WASM instructions. For example, `a + b` must become `f64.add`, loops must become WASM `loop`/`br_if`, and user-defined functions must become real WASM functions called from `_start`.

## Constraints

- Work entirely offline. All tools are pre-installed.
- Do not modify test files.
