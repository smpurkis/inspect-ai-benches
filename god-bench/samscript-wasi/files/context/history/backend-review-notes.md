# Backend review notes

Meeting series: compiler working group

Classification: discussion record; decisions required ratification elsewhere.

## 2025-04-09: numeric representation

The Cranelift experiment used `f64`, while the old WAT emitter still used
`f32`. Keeping `f32` would reduce formatter size and preserve browser-demo
snapshots. Moving to `f64` would match the interpreter and avoid rounding in
the numerical examples.

One proposal used tagged `i64 | f64` values. It made string formatting easier
for integer literals but caused `1` and `1.0` to carry distinct tags. The
language group did not want source spelling to affect equality.

Straw poll: five for binary64 only, one for tagged numbers, two abstentions.
This poll was advisory.

## 2025-06-17: entry points

Three layouts were demonstrated:

1. Export `main` and let a custom host call it.
2. Export `_start` and call an internal SamScript `main`.
3. Add a start section and export neither function.

Layout two ran in stock command-line WASI engines. Layout three ran too early
for hosts that initialized logging after instantiation. Layout one retained
compatibility with classroom fixtures.

The group recommended layout two for a future release. Classroom support
could remain a separate target rather than changing the command-line target.

## 2025-08-01: output folding

The prototype optimizer could execute pure source functions during compilation
and replace their results with data segments. This was attractive for constant
tables. It also meant a complete program could become one `fd_write`, making
it impossible to tell whether source arithmetic had been compiled.

A compromise would permit folding literal subexpressions while requiring user
functions and control flow to survive. Reviewers noted that reachability tests
would need to distinguish legitimate inlining from dead proof functions.

No final optimization policy was recorded in these notes.

## 2025-09-12: string representation

Options were `(ptr, len)` pairs, null-terminated bytes, and handles into a
runtime table. Pair values fit `fd_write` and permit embedded zero bytes.
Handles make concatenation and allocation easier but require indirect lookup.

The prototype selected `(ptr, len)` internally and a bump allocator for new
strings. Constants occupied a deterministic prefix of linear memory sorted by
first source occurrence.

Formatting remained unresolved. Ryu-style shortest formatting matched the
interpreter on tested finite values. A fixed 15-digit formatter was smaller
but failed round-trip checks near powers of two.

## 2025-11-06: imports

An engineer proposed importing only host functions reachable from source. A
hello-world module would import `fd_write` but not `proc_exit`; arithmetic with
dynamic division would import both. This produced smaller modules.

Validation owners preferred a fixed import surface so a runtime error path did
not depend on optimizer analysis. They also requested a stable memory export
name and one entry point.

The issue was sent to release review. This meeting record contains proposals,
not the ratified result.

## 2026-01-15: scope of version 1

The interpreter already supported lists, maps, modules, input, and indexing.
Implementing all of them would require a larger tagged runtime and ownership
strategy. The compiler milestone chiefly needed scalar computation, functions,
loops, conditions, and output.

Participants agreed that target conformance need not equal interpreter feature
completeness. They disagreed on whether unsupported features should trap in a
generated module or fail compilation. Compile-time rejection was easier to
diagnose and favored by the implementation team.

## 2026-03-03: release readiness

The release candidate passed stock Wasmtime and WAMR smoke tests. Remaining
items were precise division-by-zero behavior, evidence that calls remained
reachable, and wording around deterministic binary output.

The chair closed the meeting by directing implementers to the signed release
contract once published. Notes and prototypes would remain in the repository
to support regressions but would not acquire normative status.
