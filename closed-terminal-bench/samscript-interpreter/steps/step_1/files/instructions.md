# Step 1: SamScript Interpreter and Compiler

Complete the SamScript toolchain in Rust so that it can both **interpret** and **compile** SamScript programs to native executables.

## Background

SamScript is a custom dynamically-typed scripting language. A partial Rust implementation is provided at `/app/`. Read the full language specification at `/app/step_1/files/language_spec.md`.

## Starter Code

The project has the following structure:

- `Cargo.toml` — project manifest with all needed dependencies (clap, cranelift)
- `src/main.rs` — CLI skeleton with `run` and `compile` subcommands (mostly complete)
- `src/ast.rs` — **Complete** AST type definitions — you should not need to modify this
- `src/lexer.rs` — **Partial** tokenizer (~60% done). Missing: string interpolation, multi-char operators (`>=`, `<=`, `!=`, `**`, `+=`, etc.), several keyword recognitions
- `src/parser.rs` — **Stubbed** recursive-descent parser. All function bodies contain `todo!()`
- `src/interpreter.rs` — **Stubbed** tree-walking interpreter. Contains Value type definitions but `interpret()` is `todo!()`
- `src/compiler.rs` — **Stubbed** native compiler using Cranelift. `compile()` is `todo!()`
- `samples/` — sample SamScript programs for testing

## Requirements

1. **Complete the lexer** — implement string interpolation tokenizing, all multi-character operators, and all keyword recognition
2. **Implement the parser** — build a recursive-descent parser that produces the AST defined in `ast.rs`
3. **Implement the interpreter** — tree-walking interpreter that executes SamScript programs
4. **Implement the compiler** — use Cranelift to compile SamScript to native executables
5. **Interpreter-compiler parity** — both modes MUST produce identical stdout output for all valid programs

### Running programs

```bash
# Interpret a program
./target/release/samscript run samples/hello.sam

# Compile and run a program
./target/release/samscript compile samples/hello.sam -o hello
./hello
```

### Step 1 Language Features (subset)

For this step, implement:
- Number, string, bool, none types
- `let` / `const` variable declarations
- Arithmetic, comparison, and logical operators
- String interpolation with `${}`
- `if` / `else if` / `else` conditionals
- `loop` / `break` / `continue`
- Functions with default parameters and return values
- `print()` built-in
- `assert()` built-in
- Proper error messages with line numbers and stack traces
- Rejection of programs without a `main()` function

Lists, dicts, modules, and remaining built-ins are added in Step 2.

## Verification

Tests at `/app/step_1/files/tests.py`

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline inside the container. All Rust crate dependencies are pre-vendored.
- Keep outputs deterministic.
- Do not modify test files.
- The compiled binary and the interpreter must produce identical output.
