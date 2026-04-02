# Wasm/WASI Output Specification

## Target

The SamScript compiler's `--target wasm32-wasi` flag must produce a valid WebAssembly module conforming to the WASI preview1 interface.

## Required WASI Imports

The generated Wasm module must import from `wasi_snapshot_preview1`:

| Function                | Purpose                          |
|-------------------------|----------------------------------|
| `fd_write`              | Write to stdout (fd 1)           |
| `proc_exit`             | Exit with status code            |
| `args_get`              | Get command-line arguments        |
| `args_sizes_get`        | Get argument count and buffer size|

## Module Structure

```wasm
(module
  ;; WASI imports
  (import "wasi_snapshot_preview1" "fd_write" ...)
  (import "wasi_snapshot_preview1" "proc_exit" ...)

  ;; Memory export (required by WASI)
  (memory (export "memory") 1)

  ;; _start function (entry point)
  (func (export "_start") ...)
)
```

## Runtime Behavior

### Print Function
`print(value)` must write the string representation of `value` followed by `\n` to stdout using `fd_write`.

### Number Formatting
Same as interpreter: integers display without decimal point, floats display with decimals.

### Exit Code
- `0` on success
- `1` on runtime error

### String Handling
Strings are stored in linear memory. The runtime must manage a simple memory allocator (bump allocator is sufficient).

## Determinism

The Wasm output must be deterministic: compiling the same source twice must produce byte-identical `.wasm` files. This is critical for the bootstrap roundtrip test.

## Output Parity

A `.wasm` file produced by `samscript compile --target wasm32-wasi` and run via `wasmtime` must produce exactly the same stdout output as:
- `samscript run` (interpreter mode)
- `samscript compile` (native mode) followed by executing the native binary

All three execution paths must agree on output for any valid SamScript program.
