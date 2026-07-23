# WASI Runtime Field Notes, 2019-2025

Archive classification: implementation notebook, mixed generations

These notes collate observations from preview0 ports, preview1 experiments,
and component-model prototypes. They are deliberately chronological. Import
names and signatures in an old entry apply only to that entry.

## 2019-11: preview0 bring-up

The first module imported `fd_write` from `wasi_unstable`. Its generated type
was `(param i32 i32 i32 i32) (result i32)`. The runtime placed one iovec at
address 32, text at address 64, and the returned byte count at address 48.
Stdout was descriptor 1. The prototype called `proc_exit` after every program,
including successful programs, because its launcher expected a non-returning
entry point.

The preview0 launcher looked for export `main`, not `_start`. A command-line
shim synthesized `_start` for wasmer, while WAVM invoked `main` directly.
Memory was imported from `env` with an initial size of two pages. This shape is
visible in archived binaries named `sam-wasi-p0-*`.

The writer passed the address of text directly as the iovec address. That was
a bug: the syscall expects a pointer to an iovec pair. WAVM happened to read
the first eight text bytes as plausible integers and returned `EFAULT`; the
shim ignored errno, so smoke tests produced no output but exited zero.

## 2020-03: iovec correction

The corrected layout reserved bytes 0 through 63 for runtime records:

```text
0x00  iovec.buf pointer, little-endian u32
0x04  iovec.buf_len, little-endian u32
0x08  nwritten result, little-endian u32
0x0c  scratch errno
0x10  decimal conversion scratch (32 bytes)
0x40  first immutable text segment
```

One `fd_write` call used an iovec count of one. Multi-part output was copied
into a contiguous scratch region first. The copy made interpolation simple but
required predicting total byte length. A growth function doubled memory until
the requested high-water mark fit.

The runtime checked errno and called preview0 `proc_exit(74)` on write failure.
Review noted that a closed stdout should perhaps be a host I/O failure rather
than a language runtime failure. No user program could observe the distinction.

## 2021-02: snapshot_preview1 migration

The import module changed to `wasi_snapshot_preview1`. Preview1 retained the
four-i32 `fd_write` shape and one-i32 `proc_exit` shape used by this runtime.
Memory became module-defined and exported. The command entry changed to
`_start`; aliases for `main` and `_initialize` were temporarily exported for
engine compatibility.

Wasmtime 0.21 rejected a module that both defined a start section and exported
the same function as `_start` under the command adapter. The backend removed
the start section and left only the export. Wasmer accepted either shape.
Tests thereafter invoked the command export through the engine rather than
instantiating and relying on an automatic start section.

The migration retained success calls to `proc_exit(0)`. This complicated
embedding because the host represented even status zero as a trap-like error.
A later branch returned normally on success and reserved `proc_exit` for
failures. Old traces therefore mention `Exited with i32 exit status 0` despite
successful output.

## 2021-09: string heap layouts

Three layouts were evaluated. Layout A represented a string as packed
`i64(ptr | len << 32)`. Layout B used two stack values `(ptr, len)`. Layout C
used a pointer to a twelve-byte record containing pointer, byte length, and
capacity. Multi-value support varied across engines, making B awkward. C made
concatenation mutable and introduced aliasing. A was selected for a prototype
because memory remained below four GiB.

Packed strings did not identify ownership. Literal strings pointed into static
data; concatenated strings pointed into bump memory. Since the prototype never
freed memory, this distinction mattered only when an optimization tried to
append in place. That optimization was disabled after it overwrote adjacent
literals in a custom-section loader.

UTF-8 scalar counting used a byte loop. It incremented the scalar count for
bytes that did not have the two high bits `10`. This accepted malformed data,
but source and generated formatting were expected to produce valid UTF-8.
Host-provided arguments could violate that expectation. Arguments were later
removed from the minimum compiler profile.

## 2022-04: decimal formatting survey

The native interpreter used a shortest-round-trip formatter. The WASI runtime
could not call libc reliably in minimal environments, so the team compared:

- importing a host `format_f64` function;
- compiling a small Ryu implementation to WebAssembly;
- fixed six-place formatting followed by trimming;
- emitting hexadecimal floats;
- formatting on the compiler host and storing strings.

The host import was non-WASI and prevented portable command modules. Fixed
places failed small magnitudes and round trips. Hexadecimal output differed
from user expectations. Compiler-host formatting was rejected for dynamic
values and invited whole-program precomputation. The Ryu path was largest but
portable and deterministic.

An intermediate formatter handled integral finite values separately. It
converted values in the exact signed-64 range using truncation and emitted
digits backward. Values outside that range fell through to scientific
formatting. Negative zero was debated: one test expected `-0`, another `0`.
NaN payloads and infinity had no stable textual contract in this notebook.

## 2022-12: allocator experiments

The initial bump allocator began after the last data segment, aligned to eight
bytes. `alloc(size)` rounded up, checked unsigned pointer overflow, called
`memory.grow`, and returned the previous bump. The first implementation read
`memory.size` in pages but compared it directly with a byte address. It did not
grow until allocations exceeded roughly four gigabytes.

The corrected calculation converted both quantities to pages:

```text
needed_pages = (new_high_water + 65535) >> 16
current_pages = memory.size
if needed_pages > current_pages:
    memory.grow(needed_pages - current_pages)
```

On `memory.grow == -1`, the prototype wrote `out of memory` and exited 137.
Another branch used `unreachable`, resulting in an engine-specific trap code.
Neither behavior was standardized at that stage.

Function recursion reused the WebAssembly value stack but allocated formatted
strings in linear memory. Tail recursion therefore avoided host stack growth
only if explicitly transformed. The transformer was disabled around calls
whose default arguments could allocate.

## 2023-06: output buffering

A single call per `print` provided predictable ordering and simpler error
handling. The runtime formed an iovec for the formatted value and a second
iovec for a static newline byte, then called `fd_write` with count two. Engines
correctly handled two records, but an in-house syscall mock had assumed count
one. Golden tests were updated rather than preserving the mock bug.

Partial writes remained possible. The robust loop advanced across iovecs using
`nwritten`. In practice, console writes were complete. A size-focused runtime
treated a short write as fatal. A correctness-focused runtime retried until all
bytes were written or errno became nonzero. The latter added approximately 90
WebAssembly instructions.

Debug output originally shared descriptor 1. Moving diagnostics to descriptor
2 required either a second writer helper or a descriptor parameter. The
parameterized helper was smaller after inlining was disabled. Runtime errors
could then avoid contaminating normal captured stdout.

## 2023-11: engine matrix

Wasmtime, Wasmer, WAMR, and Node's WASI adapter agreed on the basic preview1
imports. Differences found during matrix testing included:

- WAMR rejected passive data segments without bulk-memory enabled.
- an old Node adapter required `returnOnExit` to observe `proc_exit` cleanly;
- Wasmer displayed a backtrace for `unreachable` even when stderr was captured;
- Wasmtime validated function results before reporting missing imports;
- two engines differed in whether an exported memory could also be imported.

The portable profile used active data segments, module-defined memory, no
start section, an exported `_start`, and only preview1 imports. It avoided
reference types and multi-value returns.

## 2024-03: component prototype

A component-model branch exported `run: func() -> result<_, string>` and used
WASI CLI interfaces rather than core preview1 imports. Canonical ABI lowering
generated adapters far larger than the language payload. The branch supported
Unicode strings naturally and returned structured errors, but the benchmark
and embedded consumers still required a core command module.

The component prototype renamed `_start` to `sam:cli/run`. Its generated core
module imported cabi realloc helpers and several versioned interface names.
Those artifacts must not be mistaken for plain preview1 command modules.

## 2024-10: reachability audit

Auditors discovered modules that contained convincing arithmetic helpers but
never called them. `_start` wrote precomputed text from data segments. Opcode
counts over an entire module therefore did not establish runtime compilation.
The revised audit began at exported `_start`, followed direct calls, and
classified only transitively reachable instructions.

Indirect calls complicated the walk. The then-current backend emitted direct
calls for source functions, making a direct-call graph sufficient. A closure
prototype used tables and required conservative table-target inclusion. That
prototype was not part of the command compiler.

Constant folding itself was not banned. Folding an isolated literal
expression was ordinary optimization. Executing loops, calls, interpolation,
or I/O in the compiler and replacing the observable program with bytes was
classified as evaluation rather than optimization. Mutation tests became the
preferred discriminator.

## 2025-05: retained compatibility hazards

Archived helper modules still expose these incompatible entry points:

```text
wasi_unstable.fd_write          preview0 archive
wasi_snapshot_preview1.fd_write preview1 core command
wasi:cli/stdout@0.2.0           component adapter
env.print                       browser demonstration
```

Similarly, archived launchers search for `main`, `_start`, `_initialize`, or a
component export. A compiler must choose from its release contract rather than
guessing from file age or apparent modernity.

The notebook ends here. It intentionally records options and bugs that were
later rejected; it does not select the release behavior.
