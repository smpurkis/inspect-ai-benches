# Bytecode VM Step 2: Add Control Flow, Comparisons, and File I/O

Extend your working VM with new opcodes for branching, looping, comparisons,
modular arithmetic, and file I/O.

## New opcodes to implement

Add these opcodes to your VM (update `opcodes.nim` and `vm.nim`):

| Opcode | Name    | Arguments                            | Description                                         |
|--------|---------|--------------------------------------|-----------------------------------------------------|
| 0x0B   | MOD     | —                                    | Pop b (top), a (second); push a mod b               |
| 0x10   | JMP     | 2 bytes (uint16 LE absolute offset)  | Unconditional jump to byte offset in file           |
| 0x11   | JZ      | 2 bytes (uint16 LE absolute offset)  | Pop top; if zero, jump to offset                    |
| 0x12   | JNZ     | 2 bytes (uint16 LE absolute offset)  | Pop top; if nonzero, jump to offset                 |
| 0x13   | CMP_LT  | —                                    | Pop b (top), a (second); push 1 if a < b, else 0    |
| 0x14   | CMP_EQ  | —                                    | Pop b (top), a (second); push 1 if a == b, else 0   |
| 0x15   | CMP_GT  | —                                    | Pop b (top), a (second); push 1 if a > b, else 0    |
| 0x20   | FWRITE  | 2 bytes (uint16 LE path length) + path | Pop string; write to file at path                 |
| 0x21   | FREAD   | 2 bytes (uint16 LE path length) + path | Read file at path; push contents as string         |

## Jump offset convention

Jump offsets are **absolute byte positions** in the `.nbc` file (the 4-byte header
starts at offset 0, so the first instruction is at offset 4).

## Error handling

- Division/modulo by zero: exit with non-zero code and an error message to stderr.
- Jump out of bounds: exit with non-zero code and an error message to stderr.
- Type mismatch (e.g., ADD on string+int): exit with non-zero code.

## Requirements

1. Implement all new opcodes listed above.
2. All step 2 test programs must produce correct output.
3. Error programs must cause the VM to exit with non-zero status.

## Verification

Tests at `/app/step_2/files/tests.py`.

## Self-verification

    python3 -m pytest /app/step_2/files/tests.py -v

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test files.
