# SamScript Stepwise Plan

This benchmark is a staged language-implementation task where the model builds
a dual-mode (interpreter + compiler) toolchain for SamScript in Rust, then
bootstraps the language into a self-hosting compiler/interpreter targeting
Wasm/WASI.


## Benchmark Summary

Suggested task name:

- `samscript-interpreter`

Core idea:

- Step 1 builds a working Rust implementation with both an interpreter mode
  (`samscript run`) and a compiler mode (`samscript compile`) targeting native
  executables.
- Step 2 extends the language with compound types, modules, a standard library,
  and hardens both modes against a hidden conformance suite. (Details TBD —
  exact scope to be refined.)
- Step 3 bootstraps the language: the SamScript compiler/interpreter is
  rewritten in SamScript itself, compiling to Wasm/WASI. The final deliverable
  is a fully self-hosting toolchain where `samscript compile samscript.sam`
  produces a Wasm binary that can itself compile and interpret SamScript
  programs.


## Language Specification

### Program Structure

- Execution begins at the `main` function; every program must define one.
- Files use the `.sam` extension.
- Top-level code outside functions is not allowed.

### Dual Execution Modes

- **Interpreter mode** (`samscript run program.sam`): reads, tokenizes, parses,
  and evaluates the program via a tree-walking interpreter.
- **Compiler mode** (`samscript compile program.sam -o program`): reads,
  tokenizes, parses, and compiles the program to a target binary. In Step 1 the
  target is native; in Step 3 the target is Wasm/WASI.
- Both modes must produce identical observable output for the same input.

### Comments

```
# This is a line comment. Everything after # is ignored.
```

### Variables and Constants

- `let` is **required** for first declaration. Bare assignment is reassignment
  only — using an undeclared name is an error, preventing typo bugs.
- `const` declares an immutable binding. Reassignment is an error.
- Variables are block-scoped (scoped to the nearest `{ }`).

```
let name = "Sam"       # mutable — can be reassigned
const pi = 3.14159     # immutable — reassignment is an error
name = "Alex"          # reassignment (no keyword)
x = 5                  # Error: undeclared variable 'x'
```

### Types

SamScript is dynamically typed. Type annotations are optional everywhere; when
provided they are checked at runtime.

| Type     | Literal examples                  | Notes                              |
|----------|-----------------------------------|------------------------------------|
| `number` | `42`, `3.14`, `-1`                | IEEE 754 double, like JavaScript   |
| `string` | `"hello"`, `'world'`              | Unicode text, single or double quotes |
| `bool`   | `true`, `false`                   |                                    |
| `none`   | `none`                            | Absence of a value                 |
| `list`   | `[1, "two", true]`               | Ordered, heterogeneous             |
| `dict`   | `{"name": "Sam", "age": 30}`     | String keys only, ordered by insertion |

### Truthiness

Python-style: `false`, `none`, `0`, `""`, `[]`, `{}` are falsy. Everything
else is truthy.

### Operators

Arithmetic: `+`, `-`, `*`, `/`, `%` (remainder), `**` (exponentiation).

Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`.

Logical: `and`, `or`, `not` (English words, short-circuit evaluation).

String: `+` (concatenation), `*` (repeat: `"ha" * 3 == "hahaha"`).

Assignment: `=`, `+=`, `-=`, `*=`, `/=`.

### String Interpolation and Escapes

Template strings with `${}` for embedded expressions:

```
let name = "world"
print("hello ${name}")              # hello world
print("2 + 2 = ${2 + 2}")          # 2 + 2 = 4
```

Standard escapes: `\n`, `\t`, `\\`, `\"`, `\'`, `\$`, `\0`.

### Control Flow

**If / else if / else:**

```
if score >= 90 {
    print("A")
} else if score >= 80 {
    print("B")
} else {
    print("C")
}
```

No parentheses required around the condition (but allowed).

**Loop (the only loop construct):**

```
loop {
    let line = input()
    if line == "quit" { break }
    print(line)
}
```

- `break` exits the loop.
- `continue` skips to the next iteration.
- All iteration is built from `loop` — there is no `for` or `while`.

### Functions

```
fn greet(name) {
    print("hello ${name}")
}

fn add(a: number, b: number) -> number {
    return a + b
}

fn repeat(text: string, times: number = 3) -> string {
    let result = ""
    let i = 0
    loop {
        if i >= times { break }
        result += text
        i += 1
    }
    return result
}
```

- `return` exits the function with a value. If omitted, the function returns
  `none`.
- Default parameters must come after non-default parameters.
- `_` is a valid discard name for unused variables.

### Blocks

Curly braces `{ }` create a scope. Variables declared inside are not visible
outside. Blocks do not return values — use `return` in functions.

### Modules and Imports

```
from math import sqrt            # from math.sam, import sqrt
from utils.strings import pad    # from utils/strings.sam, import pad
```

- Imports can reference any top-level `fn`, `let`, or `const`.
- Circular imports are an error (detected at load time).

### Built-in Functions

| Function                        | Description                              |
|---------------------------------|------------------------------------------|
| `print(values...)`             | Print values separated by spaces, then newline |
| `input(prompt: string = "")`   | Read a line from stdin, return as string |
| `len(container)`               | Length of string, list, or dict          |
| `type(value)`                  | Returns type name as string: `"number"`, `"string"`, etc. |
| `str(value)`                   | Convert to string                        |
| `num(value)`                   | Convert to number (error if not parseable) |
| `assert(condition, message="")` | Panic with message if condition is falsy |

### Error Behaviour

Errors crash the program with a stack trace. There is no try/catch.

```
Error: index out of bounds: index 5, length 3
  at get_item (utils.sam:12)
  at process  (main.sam:7)
  at main     (main.sam:2)
```

### Pipeline (File Execution)

1. Read entire source file.
2. Tokenize into token stream.
3. Parse token stream into AST.
4. Transform AST into action tree (resolve names, check imports).
5. Execute action tree (interpreter) or emit code (compiler).


## 3-Step Structure

### Step 1: Rust Implementation — Interpreter and Compiler Modes

Objective:

- Build the SamScript toolchain in Rust with two modes:
  - `samscript run <file.sam>` — tree-walking interpreter.
  - `samscript compile <file.sam> -o <output>` — compiles to a native
    executable (e.g. via Cranelift or direct machine-code emission).
- Both modes must support the core language: `let`/`const`, arithmetic,
  strings with `${}` interpolation, `bool`/`none`, `if`/`else if`/`else`,
  `loop`/`break`/`continue`, functions with defaults, `return`, and
  built-ins (`print`, `len`, `type`, `str`, `num`, `assert`).

What it tests:

- Rust systems programming
- lexer/parser/AST construction in a compiled language
- tree-walking interpreter implementation
- code generation for a native target
- CLI design with subcommands
- both modes producing identical observable behavior for the same input
- helpful error messages with file/line context and stack traces

Verification:

- public sample programs produce exact expected stdout in both modes
- `samscript run hello.sam` and `./hello` (after compile) produce identical
  output
- type errors and syntax errors produce clear error messages with line numbers
- a hidden suite of arithmetic, string, and control-flow programs all match
  reference output under both interpreter and compiler
- programs without a `main` function are rejected with a clear error
- undeclared variable assignment is an error (not implicit declaration)
- `const` reassignment is an error

Suggested visible checks:

- hello-world program runs and compiles
- arithmetic, string concatenation, and `${}` interpolation
- nested function calls with default parameters
- `loop`/`break`/`continue` patterns
- variable scoping across blocks
- `bool`/`none` truthiness in conditions
- interpreter vs compiler output parity on all public samples


### Step 2: Language Completeness and Conformance (TBD)

Objective:

- Extend both interpreter and compiler modes to support `list`, `dict` (string
  keys only), the module/import system, and the full built-in function set.
  Harden against a hidden conformance suite.

What it tests:

- list and dict construction, indexing, mutation in both modes
- module resolution (`from x import y`) including transitive imports
- circular import detection with a clear error
- edge-case handling (empty containers, nested dicts, out-of-bounds)
- compiler correctness for complex language features

Verification:

- visible and hidden programs using compound types match reference output in
  both modes
- import chains resolve correctly across multi-file programs
- circular imports are rejected (not a hang or stack overflow)
- errors produce readable stack traces
- malformed programs are rejected with helpful error messages
- interpreter and compiler produce identical output for all test programs

Note: exact scope of Step 2 is to be refined — may include additional features
such as closures or REPL mode depending on how Step 1 settles.


### Step 3: Self-Hosting Wasm/WASI Toolchain

Objective:

- Rewrite the SamScript compiler and interpreter in SamScript itself. The
  compiler mode must target Wasm/WASI, producing `.wasm` modules that run under
  a WASI-compatible runtime (e.g. wasmtime). The interpreter mode must also work
  when compiled to Wasm. The final deliverable is a fully bootstrapped,
  self-hosting toolchain:
  - `samscript compile samscript.sam -o samscript.wasm` (using the Rust
    toolchain from Steps 1-2)
  - `wasmtime samscript.wasm -- run hello.sam` produces correct output
  - `wasmtime samscript.wasm -- compile hello.sam -o hello.wasm` produces a
    valid Wasm module
  - `wasmtime samscript.wasm -- compile samscript.sam -o samscript2.wasm`
    bootstraps: the output can itself compile and interpret programs identically

What it tests:

- writing a compiler in the language it compiles (bootstrapping)
- Wasm binary format generation
- WASI runtime implementation (memory allocator, fd_write, args_get, etc.)
- interpreter-in-Wasm correctness
- bootstrap round-trip determinism
- end-to-end correctness of both modes when self-hosted

Verification:

- the Rust toolchain compiles the SamScript-written toolchain to Wasm
- `wasmtime samscript.wasm -- run <program>` matches reference output for all
  test programs
- `wasmtime samscript.wasm -- compile <program> -o out.wasm` produces valid
  Wasm; `wasmtime out.wasm` matches reference output
- bootstrap round-trip: `samscript2.wasm` (compiled by `samscript.wasm`)
  produces identical outputs to `samscript.wasm` on all test programs
- hidden test programs cover edge cases in code generation and interpretation

Suggested visible checks:

- simple programs run correctly under `wasmtime samscript.wasm -- run`
- simple programs compile correctly under `wasmtime samscript.wasm -- compile`
- compiler self-compilation produces a working Wasm binary
- bootstrap round-trip produces bit-identical Wasm output
- both interpreter and compiler modes work end-to-end in the Wasm-hosted
  toolchain


## Implementation Notes

- Step 1 should provide a partial Rust skeleton: Cargo project with the CLI
  subcommands wired up, lexer partially implemented, parser and evaluator/codegen
  stubbed. The model completes both modes.
- Step 2 layers on top of the working Step 1 toolchain with new test files and
  instructions but no new skeleton code.
- Step 3 should provide WASI ABI documentation, a wasmtime-based test harness,
  and the expectation that the model writes the entire SamScript toolchain in
  SamScript. The Rust toolchain from Steps 1-2 serves as the bootstrap compiler.
- Both modes must produce identical observable output for the same input program
  at every step. Tests should verify parity.
- All steps should use deterministic I/O so output comparison is byte-exact.
- The hidden test suite at each step should include adversarial edge cases
  (deeply nested expressions, unusual Unicode, empty programs, recursive imports).


## Suggested Folder Layout

```text
samscript-interpreter/
  PLAN.md
  eval.yaml
  run.py
  compose.yaml
  environment/
    Dockerfile
  steps/
    step_1/
      files/
        instructions.md
        tests.py
        src/
          main.rs          # CLI skeleton with run/compile subcommands
          lexer.rs         # partial implementation
          parser.rs        # stubbed
          ast.rs           # type definitions
          interpreter.rs   # stubbed
          compiler.rs      # stubbed
        Cargo.toml
        samples/
          hello.sam
          arithmetic.sam
          control_flow.sam
      hidden/
        hidden_tests.py
        hidden_samples/
    step_2/
      files/
        instructions.md
        tests.py
        samples/
      hidden/
        hidden_tests.py
        hidden_samples/
    step_3/
      files/
        instructions.md
        tests.py
        wasi_abi.md        # WASI ABI spec
        samscript_src/     # empty directory — model writes toolchain here
        samples/
      hidden/
        hidden_tests.py
        hidden_samples/
```


## Final Recommendation

This is a demanding three-step benchmark that tests Rust systems programming,
language implementation, and compiler bootstrapping. The dual-mode requirement
(interpreter + compiler) doubles the surface area at each step and forces the
model to reason about both evaluation strategies. Step 3's self-hosting
Wasm/WASI target is a strong differentiator: producing a bootstrapped toolchain
that works in both interpreter and compiler modes under Wasm is a genuinely hard
systems task. The progression from Rust implementation to SamScript self-hosting
mirrors real-world language bootstrap paths.
