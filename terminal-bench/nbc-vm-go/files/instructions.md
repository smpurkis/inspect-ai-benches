# Nim Bytecode VM in Go

Implement a stack-based bytecode virtual machine in Go that executes `.nbc` (Nim ByteCode) binary files. The .nbc format and a suite of test programs are provided.

## .nbc Binary Format

Each `.nbc` file is a sequence of instructions. Each instruction is 1 byte opcode followed by optional operands.

Read the format spec at `/app/files/nbc_format.md`.

## Required

- Build: `go build -o /app/nbcvm /app/files/`
- Run: `/app/nbcvm <program.nbc>`
- Pass all provided test programs producing correct stdout output

## Self-verification

    python3 -m pytest /app/files/tests.py -v

## Constraints

- Implement in Go from scratch
- Work entirely offline
- Do not modify test files
