# Runtime ABI migration notebook

Branch: `abi-preview0-compat`

Last updated: 2024-08-02

Disposition: abandoned after runtime working-group review.

## Purpose

The first command-line prototype targeted engines that still exposed the
`wasi_unstable` module name. This notebook records its adapters so old binary
fixtures can be inspected. It is not a statement about current output.

## Prototype imports

The adapter requested `fd_write`, `proc_exit`, `args_get`, and
`args_sizes_get` from `wasi_unstable`. A browser host supplied all four even
for modules that did not inspect arguments.

`fd_write` used four `i32` parameters and returned an `i32` errno. Iovecs were
two little-endian 32-bit words: buffer address followed by byte length.

`proc_exit` accepted one `i32` and was treated as returning no values.

The argument functions were retained because the prototype generated one
universal runtime module. Removing unused imports was not attempted.

## Exports

Prototype modules exported `mem` and `main`. The launcher called `main`
directly. A temporary compatibility patch also exported `_start` as an alias,
but it required a nonstandard host option because both entry points ran.

Memory started at two pages. Page zero held text constants from offset 4096;
page one was scratch space for formatting.

## Numeric bridge

SamScript 0.7 represented source numbers as `f32`. The JavaScript interpreter
used `Math.fround` after each arithmetic operation so browser and Wasm output
matched. Decimal output was fixed to six fractional digits, then trailing
zeroes were removed.

This representation was known to lose integer precision above 2^24. The demo
suite avoided those values. A proposed tagged `i32`/`f32` union was rejected
because it changed equality behavior.

## Printing shim

The prototype formatter converted one `f32` into a 48-byte scratch buffer.
It special-cased NaN and infinity, then emitted sign, integer digits, decimal
point, and up to six fractional digits. The host shim appended LF.

String output used one iovec at address 64 and stored the `nwritten` result at
address 72. The implementation ignored errno because demo runners treated a
closed stdout descriptor as successful termination.

## Exit handling

Runtime faults printed `trap: <message>` to stdout and called `proc_exit(255)`.
Compile diagnostics were also printed to stdout. This made snapshot tests
simple but broke shell conventions and was removed in later work.

## Compatibility observations

Wasmtime 11 accepted the old import module behind a compatibility switch.
Wasmtime 15 removed that switch from default builds. Wasmer exposed a similar
alias but rejected the duplicate start export.

Binaryen rewrote the aliased entry points differently depending on version,
so byte-for-byte deterministic builds were not possible after optimization.
The release pipeline consequently stopped running `wasm-opt`.

## Unresolved items at branch closure

- Decide whether command arguments are a language feature or launcher detail.
- Replace six-digit numeric formatting with a round-trip algorithm.
- Choose one memory export spelling.
- Define closed-pipe behavior.
- Remove browser-only host replacement for `$print_f32`.
- Port fixtures from `while` syntax to the parser's `loop` syntax.

These items moved to later design work; conclusions in this notebook were not
automatically carried forward.
