# Nim Bytecode VM Stepwise Plan

This benchmark is a staged language-runtime task centered on repairing and
extending a custom bytecode interpreter written in Nim.


## Benchmark Summary

Suggested task name:

- `nim-bytecode-vm-stepwise`

Core idea:

- Step 1 repairs the VM so it executes a public sample program.
- Step 2 extends it to a hidden conformance suite.
- Step 3 adds deterministic tracing with exact byte-for-byte logs.


## 3-Step Structure

### Step 1: Repair Interpreter Startup

Objective:

- Repair the custom bytecode interpreter so it correctly loads and executes a
  provided sample program bundle.

What it tests:

- Nim debugging
- parser/runtime correctness
- basic CLI repair

Verification:

- interpreter starts
- bytecode loads
- public sample output matches exactly
- any parse/runtime/output mismatch scores zero


### Step 2: Extend Conformance Coverage

Objective:

- Support a hidden suite of arithmetic, branching, stack, and file-I/O programs.

What it tests:

- VM semantics
- typed error handling
- malformed bytecode rejection

Verification:

- all visible and hidden programs return exact reference output and exit status
- malformed bytecode is rejected with the correct typed error


### Step 3: Deterministic Tracing Mode

Objective:

- Add a canonical trace mode that emits one deterministic log line per
  instruction.

What it tests:

- exact formatting
- instruction-order fidelity
- deterministic runtime introspection

Verification:

- trace format matches exactly
- hidden suite traces are byte-for-byte identical to reference logs
- any whitespace/opcode/order deviation scores zero


## Implementation Notes

- make the bytecode format simple enough to inspect in tests
- use visible fixture programs plus hidden variants of the same instruction set
- compare both stdout and structured exit codes
- keep tracing requirements surfaced in visible instructions, since formatting is strict


## Final Recommendation

This is a strong niche benchmark because Nim is uncommon, the VM domain is
highly verifiable, and the staged progression is clean.
