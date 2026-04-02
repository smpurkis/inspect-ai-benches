# Step 2: Language Completeness — Lists, Dicts, Modules, Built-ins

Extend both the interpreter and compiler to support the full SamScript type system and module imports.

## Requirements

1. **Lists**: `[1, 2, 3]` — creation, indexing (`list[i]`), assignment (`list[i] = x`), `len(list)`
2. **Dicts**: `{"key": value}` — creation, access (`dict["key"]`), mutation, `len(dict)`
3. **Module imports**: `from math import sqrt` — resolve `math.sam` in the same directory, import named functions
4. **Circular import detection**: `A imports B, B imports A` must produce a clear error, not hang
5. **Transitive imports**: `A imports B, B imports C` must resolve correctly
6. **All built-ins available**: `print`, `input`, `len`, `type`, `str`, `num`, `assert` must all work
7. **Nested containers**: Lists of dicts, dicts of lists, nested lists all work correctly
8. **Parity**: Interpreter and compiler must produce identical output for all programs

## Module Resolution

When a program contains `from math import sqrt`:
1. Look for `math.sam` in the same directory as the importing file
2. Parse and evaluate the module
3. Bring the named functions into the importer's scope
4. Track which modules are currently being loaded to detect circular imports

## New Sample Programs

- `samples/lists.sam` — list creation, indexing, mutation
- `samples/dicts.sam` — dict creation, access, mutation
- `samples/imports.sam` — importing from math module
- `samples/builtins.sam` — all built-in functions
- `samples/nested_containers.sam` — complex nested data structures
- `samples/modules/math.sam` — a math utility module
- `samples/modules/utils.sam` — a string/collection utility module
- `samples/modules/circular_a.sam` + `circular_b.sam` — circular import test case

## Verification

Tests at `/app/step_2/files/tests.py`

## Self-verification

    python3 -m pytest /app/step_2/files/tests.py -v

## Constraints

- Work entirely offline.
- Do not modify test files.
- Interpreter and compiler must produce identical output.
- Module resolution must use the directory of the importing file, not the CWD.
