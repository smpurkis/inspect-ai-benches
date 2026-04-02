# Bytecode VM Step 1: Fix the Nim VM

Repair a broken custom bytecode virtual machine written in Nim.

The VM reads `.nbc` (Nim ByteCode) binary files and executes them on a stack machine.
The Nim source is at `/app/step_1/files/src/` and contains **several bugs** that
prevent it from running correctly.

## Bytecode format

Every `.nbc` file starts with a 4-byte magic header: `NBC\x01` (bytes `0x4E 0x42 0x43 0x01`).
After the header is a stream of instructions, each starting with a 1-byte opcode:

| Opcode | Name      | Arguments                              | Description                        |
|--------|-----------|----------------------------------------|------------------------------------|
| 0x01   | PUSH_INT  | 4 bytes (int32 LE)                     | Push integer onto stack            |
| 0x02   | PUSH_STR  | 2 bytes (uint16 LE length) + N bytes   | Push UTF-8 string onto stack       |
| 0x03   | ADD       | —                                      | Pop two ints, push sum             |
| 0x04   | SUB       | —                                      | Pop b (top), a (second); push a−b  |
| 0x05   | MUL       | —                                      | Pop two ints, push product         |
| 0x06   | DIV       | —                                      | Pop b (top), a (second); push a÷b  |
| 0x07   | PRINT     | —                                      | Pop and print to stdout (no newline)|
| 0x08   | PRINTLN   | —                                      | Pop and print with newline         |
| 0x09   | DUP       | —                                      | Duplicate top of stack             |
| 0x0A   | POP       | —                                      | Discard top of stack               |
| 0x0C   | SWAP      | —                                      | Swap top two stack elements        |
| 0x0D   | OVER      | —                                      | Copy second element to top         |
| 0xFF   | HALT      | —                                      | Stop execution                     |

PRINT and PRINTLN must handle **both** integer and string values.

## Source files

- `src/main.nim` — CLI entry point; runs `nbcvm <file.nbc>`
- `src/parser.nim` — Loads and validates the `.nbc` file header
- `src/vm.nim` — Stack-based execution engine
- `src/opcodes.nim` — Opcode constants and `Value` type definitions

## Requirements

1. Fix all bugs so the VM compiles and runs correctly.
2. The binary must accept a single command-line argument (the `.nbc` file path).
3. Running with no arguments must print a usage message to stderr and exit 1.
4. Running with an invalid `.nbc` file must exit with a non-zero code.
5. Test programs in `/app/step_1/files/programs/` must produce correct output.

## Verification

Tests at `/app/step_1/files/tests.py`.

## Self-verification (important!)

Before completing this step, verify your solution:

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Scoring

- Step 1 fail: 0
- Step 1 pass, Step 2 fail: 1/3
- Step 1+2 pass, Step 3 fail: 2/3
- All pass: 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
