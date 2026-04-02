# NBC Binary Format Specification

## File Header

Every `.nbc` file begins with a 4-byte header:

| Offset | Size | Value        | Description          |
|--------|------|--------------|----------------------|
| 0      | 3    | `NBC` (ASCII)| Magic bytes          |
| 3      | 1    | `0x01`       | Format version       |

All multi-byte integers are **little-endian**.

## Instructions

Instructions follow immediately after the 4-byte header. Each instruction is:
1. One **opcode byte**
2. Zero or more **operand bytes** depending on the opcode

### Operand Types

| Type   | Size    | Description                                      |
|--------|---------|--------------------------------------------------|
| `i32`  | 4 bytes | Signed 32-bit integer (little-endian)            |
| `u16`  | 2 bytes | Unsigned 16-bit integer (little-endian)          |
| `str`  | variable| `u16` length prefix followed by UTF-8 bytes     |
| `path` | variable| `u16` length prefix followed by UTF-8 path bytes|

### Opcode Table

| Opcode | Mnemonic      | Operand | Stack Effect                         | Description                                    |
|--------|---------------|---------|--------------------------------------|------------------------------------------------|
| `0x01` | `PUSH_INT`    | `i32`   | `( -- n)`                            | Push 32-bit integer constant                   |
| `0x02` | `PUSH_STR`    | `str`   | `( -- s)`                            | Push string constant                           |
| `0x03` | `ADD`         | –       | `(a b -- a+b)`                       | Integer addition                               |
| `0x04` | `SUB`         | –       | `(a b -- a-b)` *                     | Integer subtraction; pops b then a, pushes a-b |
| `0x05` | `MUL`         | –       | `(a b -- a*b)`                       | Integer multiplication                         |
| `0x06` | `DIV`         | –       | `(a b -- a/b)` *                     | Integer division; pops b then a, pushes a/b; error on b=0 |
| `0x07` | `PRINT`       | –       | `(v -- )`                            | Print value to stdout (no newline); any type   |
| `0x08` | `PRINTLN`     | –       | `(v -- )`                            | Print value to stdout with newline; any type   |
| `0x09` | `DUP`         | –       | `(a -- a a)`                         | Duplicate top of stack                         |
| `0x0A` | `POP`         | –       | `(a -- )`                            | Discard top of stack                           |
| `0x0C` | `SWAP`        | –       | `(a b -- b a)`                       | Swap top two elements                          |
| `0x0D` | `OVER`        | –       | `(a b -- a b a)`                     | Copy second element to top                     |
| `0x10` | `JUMP`        | `u16`   | `( -- )`                             | Unconditional jump to absolute byte offset     |
| `0x11` | `JUMP_IF_Z`   | `u16`   | `(cond -- )`                         | Pop cond; jump if cond == 0                    |
| `0x12` | `JUMP_IF_NZ`  | `u16`   | `(cond -- )`                         | Pop cond; jump if cond != 0                    |
| `0x13` | `LT`          | –       | `(a b -- (a<b ? 1 : 0))`             | Less-than comparison                           |
| `0x14` | `GT`          | –       | `(a b -- (a>b ? 1 : 0))`             | Greater-than comparison                        |
| `0x15` | `EQ`          | –       | `(a b -- (a==b ? 1 : 0))`            | Equality comparison                            |
| `0x20` | `FILE_WRITE`  | `path`  | `(content -- )`                      | Pop string, write to inline path operand       |
| `0x21` | `FILE_READ`   | `path`  | `( -- content)`                      | Read inline path operand, push file contents   |
| `0xFF` | `HALT`        | –       | `( -- )`                             | Stop execution; exit code 0                    |

*Note: For SUB, the stack before is `[a, b]` where b is on top; result is `a - b`.
For DIV, result is `a / b` (integer division, truncated toward zero).

## Jump Targets

Jump operands are **absolute byte offsets** from the start of the file (same coordinate space as `ip`).

## PRINT / PRINTLN

Both `PRINT` and `PRINTLN` accept any value type (integer or string) and convert it to its decimal/string representation before printing.

## Error Conditions

The VM must exit with a non-zero status and write a descriptive message to stderr on:
- Stack underflow (pop/peek on empty stack)
- Type error (e.g. ADD with non-integer operands)
- Division by zero
- Out-of-bounds jump target
- File I/O errors

## Example: hello.nbc

```
4e 42 43 01          ; magic + version
02 0d 00             ; PUSH_STR, length=13
48 65 6c 6c 6f 2c 20 57 6f 72 6c 64 21  ; "Hello, World!"
08                   ; PRINTLN
ff                   ; HALT
```

Output: `Hello, World!`
