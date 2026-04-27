# SamScript Bootstrap — Self-Interpreter

Write a SamScript program that implements a SamScript interpreter in SamScript itself.

## Overview

A complete SamScript interpreter is pre-built at `/app/target/release/samscript`. It can run `.sam` programs:

```bash
./target/release/samscript run samples/hello.sam
# Output: hello world
```

Your task: write `/app/samscript_bootstrap.sam` — a SamScript program that, when run by the reference interpreter, can itself interpret arbitrary SamScript programs.

```bash
# Direct execution (reference interpreter)
./target/release/samscript run samples/hello.sam

# Bootstrap execution (your interpreter, run via reference)
./target/release/samscript run samscript_bootstrap.sam -- run samples/hello.sam
```

Both commands must produce **identical output** for any valid SamScript program.

## How it works

The reference interpreter provides two builtins for bootstrapping:

- **`read_file(path)`** — reads a file and returns its contents as a string
- **`args()`** — returns command-line arguments passed after `--` as a list of strings

Your bootstrap interpreter should:
1. Call `args()` to get `["run", "samples/hello.sam"]`
2. Call `read_file("samples/hello.sam")` to read the source code
3. Lex, parse, and interpret the source code, producing the same output

## Language Reference

See `/app/files/language_spec.md` for the complete SamScript language specification.

Key features your bootstrap must handle:
- All value types: numbers (f64), strings (with `${}` interpolation), bools, none, lists, dicts
- All operators: arithmetic (`+`, `-`, `*`, `/`, `%`, `**`), comparison, logical (`and`, `or`, `not`), string concat (`..`)
- Variable declarations (`let`, `const`) and assignment (including compound: `+=`, `-=`, etc.)
- Control flow: `if`/`else if`/`else`, `loop`/`break`/`continue`
- Functions with default parameters and `return`
- String indexing: `str[i]` returns a single-character string
- Built-in functions: `print`, `len`, `type`, `str`, `num`, `assert`
- `main()` entry point

## Important notes

- The interpreter source code at `/app/src/` is **read-only**. Do not attempt to modify it.
- Your bootstrap must be a single file at `/app/samscript_bootstrap.sam`.
- The bootstrap must produce **exactly the same output** as the reference interpreter for all valid programs. This includes exact number formatting (integers print without decimals: `10.0` prints as `10`).

## Verification

Tests at `/app/files/tests.py`

```bash
python3 -m pytest /app/files/tests.py -v
```

## Constraints

- Work entirely offline. All tools are pre-installed.
- Do not modify test files or the interpreter source.
- Your solution must be a SamScript program — no other languages.
