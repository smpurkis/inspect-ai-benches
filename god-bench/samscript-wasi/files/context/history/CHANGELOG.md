# SamScript toolchain history

This chronology combines release tags and branch closure notes. Only entries
marked released were shipped; prototypes and candidates may contradict later
decisions.

## 0.6.0 - released 2023-11-10

- Added a teaching interpreter with integer numbers and top-level statements.
- Added `while` and a native `print_num` host callback.
- Function declarations became visible in source order.
- No WebAssembly output was distributed.

## 0.7.0-wasm-demo - prototype 2024-02-14

- Added the first WAT emitter for a browser demonstration.
- Represented all backend numbers as `f32`.
- Imported `fd_write` from `wasi_unstable` in command-line experiments.
- Exported `main` and `mem`; a JavaScript launcher called `main`.
- Constant-folded complete worksheet programs.
- This tag was never declared a language release.

## 0.8.0-classroom - candidate 2024-06-03

- Tested mixed integer and floating numeric values in the native compiler.
- Added custom `sam_runtime` imports for classroom runners.
- Documented dynamic scope and mutable `const` as temporary limitations.
- Added dead opcode-coverage helpers after aggressive constant folding.
- Candidate withdrawn because native and Wasm behavior differed.

## preview0-compat - abandoned 2024-08-02

- Added `_start` as an alias while retaining `main`.
- Kept `wasi_unstable` for old engines.
- Fixed stdout buffer corruption in the browser shim.
- Branch closed when supported engines removed preview0 aliases.

## 0.9.0 - interpreter release 2025-01-20

- Switched the interpreter numeric representation to binary64.
- Replaced `while` with `loop`, `break`, and `continue`.
- Added lexical blocks, immutable `const`, and declaration hoisting.
- Added `${expression}` interpolation and the `..` concatenation operator.
- Added lists, dictionaries, imports, stdin, indexing, and stack traces.
- This was an interpreter release; it did not define target-specific ABI.

## compiler-spike-2 - prototype 2025-05-11

- Generated preview1 imports and a `_start` entry point.
- Used host-side formatting while exploring runtime layout.
- Implemented `f64` arithmetic and structured loops.
- Still evaluated interpolation containing function calls at compile time.
- Rejected as a release because output computation was not always reachable.

## 1.0.0-rc1 - candidate 2025-10-08

- Defined a required compiler subset smaller than the interpreter language.
- Required runtime-reachable arithmetic, calls, and control flow.
- Selected deterministic shortest round-trip numeric formatting.
- Required byte-identical modules for repeated compilation.
- Proposed optional preview2 component output under a second target name.

## 1.0.0-rc2 - candidate 2026-01-29

- Removed preview2 from the initial release.
- Required preview1 `fd_write` and `proc_exit` only when used.
- Review found that conditional imports made structural validation brittle.
- Deferred lists, dictionaries, imports, stdin, and indexing.
- Clarified that scalar string length counts Unicode scalar values.

## 1.0.0 - released 2026-03-18

- Published one target contract for `wasm32-wasi` snapshot preview1.
- Standardized deterministic module shape and runtime failure status.
- Required imports and exports independent of source feature use.
- Prohibited whole-program output folding and unreachable proof code.
- Confirmed binary64 arithmetic and right-associative exponentiation.
- Confirmed lexical bindings, boolean conditions, and short-circuit logic.
- Release details live in the release contract, not this chronology.

## post-1.0 proposals - unreleased

- Consider preview2 components and canonical ABI strings.
- Consider list and dictionary lowering after a garbage collector is chosen.
- Consider preserving stack traces in a custom debug section.
- Consider source maps for compile and runtime diagnostics.
- Consider optimization after reachability-based conformance is stable.

No post-1.0 proposal changes the 1.0 target unless a later released contract
explicitly says so.
