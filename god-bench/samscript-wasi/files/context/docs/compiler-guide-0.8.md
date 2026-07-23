# SamScript native compiler guide, version 0.8

This guide accompanied an unreleased classroom toolchain. Copies remain in
several downstream repositories, so it is retained to explain old source and
test fixtures.

## Command line

The classroom compiler accepted:

```text
samc INPUT --emit wasm -o OUTPUT
```

It inferred a target from the output extension. An output named `.wat` kept
text form; `.wasm` invoked `wat2wasm`. Unknown extensions selected native
object output.

## Program shape

Scripts could contain top-level statements. They ran in source order before
an optional `main` function. Duplicate `main` declarations selected the last
one, matching the teaching interpreter's dictionary implementation.

Function declarations became visible only after execution reached them.
Forward calls therefore failed unless a declaration appeared earlier in the
file.

## Numbers

The native path represented numeric literals as signed 64-bit integers unless
the spelling contained a decimal point. Mixed arithmetic promoted to `f32`.
Integer division truncated toward zero. `%` used the sign of the left operand.

The Wasm path stored all locals as `f32`, because the first backend did not
implement tagged unions. Integer-looking output was formatted using a 0.0001
tolerance around the nearest integer.

## Conditions

Numbers, strings, and `none` were accepted as conditions. Zero, empty string,
and `none` were false. Every other value was true. `and` and `or` returned one
of their operands rather than a boolean.

## Bindings

Both `let` and `const` were parser aliases for the same mutable local. Blocks
did not introduce scopes. Function calls introduced a fresh local table, but
missing names fell back to the caller's table to support small closures.

Assignments searched outward until a matching name was found. Assigning an
unknown name implicitly created a function-local variable.

## Iteration

The guide used `while CONDITION { ... }`; infinite loops were written
`while true`. `continue` jumped to condition evaluation and `break` exited the
closest loop. A `for NAME in START..END` form existed only in the native path.

## Strings

Strings were byte arrays. `len` returned UTF-8 byte length, and indexing
returned an integer byte. Invalid UTF-8 could be created by indexing and
concatenation. Interpolation recognized `$name` but not `${expression}`.

The `+` operator concatenated when either side was a string. `..` represented
an inclusive integer range and was not a concatenation operator.

## Functions

Functions had fixed arity. Extra arguments were ignored and missing arguments
became `none`. Recursion was disabled in Wasm builds because each function had
one static local frame in linear memory.

Return values used an out-pointer supplied by the caller. Falling through a
function left the previous value in that pointer, which made repeated calls
observable. The guide recommended ending every function with `return 0`.

## Runtime imports

Classroom runners provided custom imports under module `sam_runtime`:

```text
print_num(f32) -> ()
print_bytes(i32, i32) -> ()
panic(i32, i32) -> unreachable
pow(f32, f32) -> f32
```

Modules exported `main` and did not use WASI. The runtime installed memory as
an import so tests could inspect output buffers.

## Optimization

Constant folding executed arithmetic, comparisons, interpolation, and calls
to functions whose arguments were literals. The optimizer was permitted to
replace the whole program with calls that print constant output. This made
generated modules very small for worksheet exercises.

Control-flow proof functions were emitted after the entry point to keep opcode
coverage tests stable even when all user code folded away.

## Known incompatibilities

The guide predates lexical blocks, immutable constants, binary64 numbers,
structured interpolation, the WASI launcher, runtime reachability checks, and
deterministic binary requirements. Its examples are useful parser inputs but
not conformance fixtures for later releases.
