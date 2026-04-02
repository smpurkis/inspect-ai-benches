# Step 3: Self-Hosting Wasm/WASI Toolchain

Extend the SamScript compiler to target **WebAssembly (Wasm/WASI)**, then bootstrap the toolchain by compiling a SamScript implementation of the toolchain to Wasm.

## Overview

In this step, you will:
1. Add a `--target wasm32-wasi` flag to the `compile` subcommand
2. Write a SamScript implementation of the SamScript toolchain (in `.sam` files)
3. Use the Rust toolchain to compile the SamScript toolchain to `samscript.wasm`
4. Verify that `samscript.wasm` can interpret and compile SamScript programs
5. Bootstrap: use `samscript.wasm` to compile its own source, producing `samscript2.wasm`
6. Verify `samscript2.wasm` produces identical output to `samscript.wasm`

## Requirements

### Wasm Compilation Target

Add support for compiling to Wasm/WASI:

```bash
# Compile to native (existing)
./target/release/samscript compile hello.sam -o hello

# Compile to wasm (new)
./target/release/samscript compile hello.sam -o hello.wasm --target wasm32-wasi

# Run the wasm binary
wasmtime hello.wasm
```

The Wasm output must be a valid WASI module that can be run with `wasmtime`. It should:
- Support `fd_write` for stdout output
- Support `proc_exit` for exit codes
- Support `args_get` / `args_sizes_get` for CLI argument access
- Produce identical stdout output to the native version

### Self-Hosting SamScript Toolchain

Write a SamScript program that implements a minimal SamScript toolchain. This program should:
- Parse SamScript source code
- Interpret it with `run` subcommand
- Emit Wasm bytecode with `compile` subcommand

The self-hosted toolchain does NOT need to support all features — a subset sufficient to compile simple programs (hello, arithmetic) is acceptable.

Place the self-hosted toolchain source at `/app/samscript_bootstrap.sam`.

### Bootstrap Process

```bash
# Step A: Compile the SamScript toolchain to wasm using the Rust compiler
./target/release/samscript compile samscript_bootstrap.sam -o samscript.wasm --target wasm32-wasi

# Step B: Use samscript.wasm to interpret a simple program
wasmtime samscript.wasm -- run samples/hello.sam

# Step C: Use samscript.wasm to compile a simple program
wasmtime samscript.wasm -- compile samples/hello.sam -o hello_from_wasm.wasm
wasmtime hello_from_wasm.wasm

# Step D: Bootstrap — samscript.wasm compiles its own source
wasmtime samscript.wasm -- compile samscript_bootstrap.sam -o samscript2.wasm --target wasm32-wasi

# Step E: Verify samscript2.wasm produces same output as samscript.wasm
wasmtime samscript2.wasm -- run samples/hello.sam
```

## Specification

See `/app/step_3/files/wasi_spec.md` for Wasm/WASI output format details.

## Verification

Tests at `/app/step_3/files/tests.py`

## Self-verification

    python3 -m pytest /app/step_3/files/tests.py -v

## Constraints

- Work entirely offline. `wasmtime` is pre-installed.
- The Wasm target `wasm32-wasip1` is pre-installed via rustup.
- Do not modify test files.
- The self-hosted toolchain may support a subset of SamScript, but must handle at least: print, string literals, number literals, arithmetic, function declarations, and main() entry point.
