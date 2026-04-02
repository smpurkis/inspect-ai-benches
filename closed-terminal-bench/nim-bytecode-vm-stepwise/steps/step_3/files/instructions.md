# Bytecode VM Step 3: Execution Tracing

Add a `--trace <filename>` flag that records every executed instruction to a file.

## Usage

    nbcvm program.nbc --trace trace_output.txt

When `--trace` is specified, the VM writes one line per executed instruction to the
trace file. Normal stdout output must be **unaffected** by the trace flag.

## Trace format

Each line has the format:

    [NNNN] XXXX: OPNAME args | stack: [values]

Where:

- `NNNN` — step counter, 4-digit zero-padded decimal (starting from 1)
- `XXXX` — instruction byte offset in the file, 4-digit zero-padded lowercase hex
- `OPNAME` — uppercase opcode name (PUSH_INT, PUSH_STR, ADD, SUB, etc.)
- `args` — opcode arguments (see below)
- `values` — stack contents bottom-to-top **after** the instruction executes

### Argument formatting

| Opcode            | Args format                         |
|-------------------|-------------------------------------|
| PUSH_INT          | decimal integer (e.g., `42`)        |
| PUSH_STR          | double-quoted string (`"hello"`)    |
| JMP, JZ, JNZ      | 4-digit lowercase hex target        |
| FWRITE, FREAD     | double-quoted path                  |
| All others        | (no args)                           |

### Stack value formatting

- Integers: plain decimal (e.g., `42`)
- Strings: double-quoted (e.g., `"hello"`)

### Example

For `hello.nbc` (PUSH_STR "Hello, World!", PRINTLN, HALT):

    [0001] 0004: PUSH_STR "Hello, World!" | stack: ["Hello, World!"]
    [0002] 0014: PRINTLN | stack: []
    [0003] 0015: HALT | stack: []

## Error behavior

If the VM encounters a runtime error (e.g., division by zero), the trace file should
contain all instructions that executed successfully before the error. The erroring
instruction is **not** included in the trace.

## Requirements

1. Add `--trace <filename>` flag support to the CLI.
2. Trace output must exactly match the format above (byte-identical).
3. The trace must not alter stdout output.
4. Trace must be deterministic — running twice produces identical output.

## Verification

Tests at `/app/step_3/files/tests.py`.

## Self-verification

    python3 -m pytest /app/step_3/files/tests.py -v

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
