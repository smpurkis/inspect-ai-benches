# SamScript 1.0 to WASI Release Contract

Status: RELEASED

Release: 1.0.0

Target: `wasm32-wasi` (WASI snapshot preview1)

Normative date: 2026-03-18

## Release authority

This file is the sole normative source for the SamScript 1.0 WASI target.

When code, archived documentation, ABI notes, examples, or meeting records disagree with this file, this file wins.

Examples are informative unless a rule below explicitly incorporates them.

## Invocation and artifact

The compiler accepts `compile INPUT -o OUTPUT --target wasm32-wasi`.

A successful compile writes one valid WebAssembly binary to `OUTPUT` and exits zero.

Compilation failure exits nonzero and must not leave a successful-looking output artifact.

Compiling identical bytes with identical arguments produces byte-identical output.

The compiler operates offline and must not execute the SamScript program to discover its output.

## Source model

A program contains top-level `fn` declarations and execution calls `main()` with no arguments.

Function declarations are visible regardless of declaration order.

Statements are separated by newlines; braces delimit blocks and may contain newlines freely.

Line comments begin with `//` and end at the next newline.

Identifiers begin with ASCII letter or underscore and continue with ASCII letters, digits, or underscore.

## Values

All numeric values are IEEE-754 binary64 (`f64`); source integer spelling does not create an integer type.

Other required values are UTF-8 strings, booleans, and `none`.

Lists and dictionaries belong to the language but are outside the required WASI 1.0 compilation subset.

Boolean conditions require booleans; numeric truthiness is not defined.

`none` is returned by a function that reaches its end or uses bare `return`.

## Bindings and calls

`let` creates a mutable block-scoped binding; `const` creates an immutable block-scoped binding.

Reading an undeclared binding or assigning a `const` is an error.

Parameters are local bindings and arguments are evaluated left to right.

Default parameters are evaluated at call time after earlier parameters have been bound.

Calls use lexical function names; recursion and forward calls are supported.

`return EXPR` exits the current function with the evaluated value.

## Operators

From low to high precedence: `or`; `and`; `== !=`; `< > <= >=`; `+ - ..`; `* / %`; `**`; unary `- not`; calls.

Exponentiation `**` is right-associative. Other binary operators are left-associative.

Arithmetic `+ - * / % **` consumes and returns `f64` values.

Division or remainder by positive or negative zero is a runtime error with exit status 1.

Comparisons return booleans. Numeric comparisons use WebAssembly ordered `f64` comparison behavior.

`and` and `or` short-circuit and do not evaluate the unused operand.

`not` consumes a boolean. Unary minus consumes a number.

`..` converts each operand using `str` and concatenates the results.

Compound assignment evaluates the right side once and is equivalent to assignment with the named arithmetic operator.

## Control flow

`if CONDITION { ... } else if CONDITION { ... } else { ... }` executes at most one branch.

`loop { ... }` repeats until `break`, `return`, or a runtime error.

`break` and `continue` apply to the nearest enclosing loop.

Bindings introduced in a branch or loop body do not escape that block.

## Strings and formatting

String literals use double quotes and recognize `\n`, `\t`, `\\`, `\"`, and `\$`.

`${EXPR}` inside a string evaluates the expression at runtime and inserts its `str` result.

String concatenation and interpolation preserve UTF-8 bytes.

`print(VALUE)` writes `str(VALUE)` followed by one LF byte.

`str(true)`, `str(false)`, and `str(none)` are `true`, `false`, and `none`.

Finite integral `f64` values format without a decimal suffix; other finite values use deterministic shortest round-trippable decimal formatting.

`len(STRING)` returns the number of Unicode scalar values as an `f64`.

`type` returns `number`, `string`, `bool`, or `none` for the required subset.

`num(STRING)` parses a complete decimal number or raises a runtime error.

## WebAssembly shape

Generated modules import `fd_write` and `proc_exit` from `wasi_snapshot_preview1` with preview1 signatures.

The module exports linear `memory` and a no-argument `_start` function.

`_start` invokes compiled `main`; normal completion returns to the host with status 0.

Runtime failures call `proc_exit(1)` or otherwise terminate with process status 1.

Stdout is file descriptor 1 and is written through preview1 `fd_write` iovecs in linear memory.

One initial memory page is sufficient; a deterministic bump allocator may grow memory when needed.

Source functions and operations must be represented by instructions reachable from `_start`.

Arithmetic source operations compile to corresponding `f64` instructions or reachable runtime helpers.

Loops and conditionals compile to reachable structured control flow.

User functions compile to reachable WebAssembly functions or may be deterministically inlined.

Dead instructions do not establish conformance, and precomputing source output during compilation is forbidden.

## Required diagnostics

Unsupported syntax and malformed source are compile-time errors.

Division by a literal zero may be diagnosed at compile time if the diagnostic identifies division by zero.

Dynamic division by zero remains a runtime check.

Diagnostics go to stderr, not into the generated module's normal stdout.

No stack trace format is required for this target.

## Conformance boundary

The required subset includes numbers, strings, booleans, variables, functions, returns, conditionals, loops, break, continue, interpolation, listed operators, and listed builtins.

Imports, stdin, lists, dictionaries, indexing, and user-visible heap management are not required by this target release.

This boundary supersedes broader interpreter documentation and narrower prototype compiler notes.
