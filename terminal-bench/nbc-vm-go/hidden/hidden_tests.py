"""Hidden tests for nbc-vm-go: additional correctness checks.

These tests verify edge cases and more complex programs.
"""

import subprocess
import os
import tempfile
import struct
import pytest

FILES = "/app/files"
VM = "/app/nbcvm"


def run_nbc(prog_path, *, timeout=15):
    result = subprocess.run(
        [VM, prog_path],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def run_nbc_bytes(bytecode: bytes, *, timeout=10):
    """Write bytecode to a temp file and run it."""
    with tempfile.NamedTemporaryFile(suffix=".nbc", delete=False) as f:
        f.write(bytecode)
        path = f.name
    try:
        return run_nbc(path, timeout=timeout)
    finally:
        os.unlink(path)


def nbc(instructions: bytes) -> bytes:
    """Wrap instructions with the NBC\x01 header."""
    return b"NBC\x01" + instructions


def push_int(n: int) -> bytes:
    return b"\x01" + struct.pack("<i", n)


def push_str(s: str) -> bytes:
    b = s.encode()
    return b"\x02" + struct.pack("<H", len(b)) + b


def jump(offset: int) -> bytes:
    return b"\x10" + struct.pack("<H", offset)


def jump_if_z(offset: int) -> bytes:
    return b"\x11" + struct.pack("<H", offset)


def jump_if_nz(offset: int) -> bytes:
    return b"\x12" + struct.pack("<H", offset)


HALT = b"\xff"
ADD = b"\x03"
SUB = b"\x04"
MUL = b"\x05"
DIV = b"\x06"
PRINT = b"\x07"
PRINTLN = b"\x08"
DUP = b"\x09"
POP = b"\x0a"
SWAP = b"\x0c"
OVER = b"\x0d"
LT = b"\x13"
GT = b"\x14"
EQ = b"\x15"


# ---------------------------------------------------------------------------
# VM exists and was built
# ---------------------------------------------------------------------------

def test_vm_binary_exists():
    assert os.path.isfile(VM), f"{VM} not found — did the agent run 'go build'?"
    assert os.access(VM, os.X_OK), f"{VM} is not executable"


# ---------------------------------------------------------------------------
# Synthesised programs: arithmetic
# ---------------------------------------------------------------------------

def test_synth_push_and_println():
    """Simple PUSH_INT + PRINTLN."""
    prog = nbc(push_int(42) + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "42"


def test_synth_sub_order():
    """SUB: stack [a, b] b on top → result = a - b."""
    # push 10, push 3, SUB → 10-3=7
    prog = nbc(push_int(10) + push_int(3) + SUB + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "7"


def test_synth_div_order():
    """DIV: stack [a, b] → a/b (integer, truncated toward zero)."""
    # push 20, push 4, DIV → 5
    prog = nbc(push_int(20) + push_int(4) + DIV + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "5"


def test_synth_div_truncate():
    """Integer division truncates toward zero: 7/2=3, -7/2=-3."""
    prog = nbc(push_int(7) + push_int(2) + DIV + PRINTLN +
               push_int(-7) + push_int(2) + DIV + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    lines = out.strip().splitlines()
    assert lines == ["3", "-3"], f"got {lines}"


def test_synth_negative_ints():
    prog = nbc(push_int(-100) + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "-100"


def test_synth_mul_large():
    prog = nbc(push_int(1000) + push_int(1000) + MUL + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "1000000"


# ---------------------------------------------------------------------------
# Stack operations
# ---------------------------------------------------------------------------

def test_synth_dup():
    """DUP: (a -- a a)."""
    prog = nbc(push_int(7) + DUP + ADD + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "14"


def test_synth_pop():
    """POP discards top of stack."""
    prog = nbc(push_int(1) + push_int(2) + POP + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "1"


def test_synth_swap():
    """SWAP: (a b -- b a) — SUB gives b-a with swapped order."""
    # push 3, push 10, SWAP → stack [10, 3], SUB → 10-3=7? No:
    # After SWAP: [10, 3] with 3 on top. SUB: a=10, b=3 → 10-3=7
    prog = nbc(push_int(3) + push_int(10) + SWAP + SUB + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "7", f"SWAP+SUB expected 7, got {out.strip()!r}"


def test_synth_over():
    """OVER: (a b -- a b a) copies second element to top."""
    # push 5, push 3, OVER → [5, 3, 5], ADD top two → [5, 8]
    prog = nbc(push_int(5) + push_int(3) + OVER + ADD + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "8", f"OVER+ADD expected 8, got {out.strip()!r}"


# ---------------------------------------------------------------------------
# Comparisons synthesised
# ---------------------------------------------------------------------------

def test_synth_lt_true():
    prog = nbc(push_int(1) + push_int(2) + LT + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "1"


def test_synth_lt_false():
    prog = nbc(push_int(5) + push_int(5) + LT + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "0"


def test_synth_gt_true():
    prog = nbc(push_int(9) + push_int(3) + GT + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "1"


def test_synth_eq_equal():
    prog = nbc(push_int(7) + push_int(7) + EQ + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "1"


# ---------------------------------------------------------------------------
# Branching synthesised
# ---------------------------------------------------------------------------

def test_synth_jump_if_z_taken():
    """JUMP_IF_Z taken when condition is 0: jump over PRINTLN 99."""
    # push 0, JUMP_IF_Z to HALT (skip PRINTLN 99), PRINTLN 99, HALT
    header_size = 4
    # Lay out: push_int(0) [5 bytes] + jump_if_z(?) [3 bytes] + push_int(99) [5 bytes] + PRINTLN [1 byte] + HALT [1 byte]
    # jump target = header_size + 5 + 3 + 5 + 1 = 18
    target = header_size + 5 + 3 + 5 + 1
    prog = nbc(push_int(0) + jump_if_z(target) + push_int(99) + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "", f"JUMP_IF_Z should have skipped println, got {out!r}"


def test_synth_jump_if_nz_taken():
    """JUMP_IF_NZ taken when condition is non-zero."""
    # push 1, JUMP_IF_NZ to PRINTLN "ok", (unreachable PRINTLN "bad"), PRINTLN "ok", HALT
    # Build:
    # [4] push_int(1) [5]
    # [9] jump_if_nz(target) [3]
    # [12] push_str("bad") [3+3=6: opcode+len+3chars]
    # [18] PRINTLN [1]
    # [19] target: push_str("ok") [3+2=5]
    # [24] PRINTLN [1]
    # [25] HALT
    target = 4 + 5 + 3 + len(push_str("bad")) + 1
    prog = nbc(
        push_int(1) + jump_if_nz(target) +
        push_str("bad") + PRINTLN +
        push_str("ok") + PRINTLN + HALT
    )
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == "ok", f"expected 'ok', got {out!r}"


def test_synth_unconditional_jump():
    """JUMP always taken."""
    target = 4 + 3  # header + JUMP instruction itself
    # Immediate HALT after JUMP
    prog = nbc(jump(target) + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out == ""


# ---------------------------------------------------------------------------
# String operations
# ---------------------------------------------------------------------------

def test_synth_print_no_newline():
    """PRINT does not add newline; PRINTLN does."""
    prog = nbc(push_str("a") + PRINT + push_str("b") + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out == "ab\n"


def test_synth_long_string():
    s = "x" * 200
    prog = nbc(push_str(s) + PRINTLN + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0
    assert out.strip() == s


# ---------------------------------------------------------------------------
# File I/O synthesised
# ---------------------------------------------------------------------------

def test_synth_file_roundtrip():
    """Write a string to a file and read it back."""
    path = "/tmp/hidden_nbc_test.txt"

    def file_write_instr(p: str) -> bytes:
        pb = p.encode()
        return b"\x20" + struct.pack("<H", len(pb)) + pb

    def file_read_instr(p: str) -> bytes:
        pb = p.encode()
        return b"\x21" + struct.pack("<H", len(pb)) + pb

    content = "roundtrip-ok"
    prog = nbc(
        push_str(content) +
        file_write_instr(path) +
        file_read_instr(path) +
        PRINTLN + HALT
    )
    if os.path.exists(path):
        os.remove(path)
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == content


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------

def test_stack_underflow():
    """Popping from empty stack must fail non-zero."""
    prog = nbc(POP + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc != 0
    assert err.strip() != ""


def test_add_underflow():
    """ADD with only one value on stack must fail."""
    prog = nbc(push_int(1) + ADD + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc != 0


def test_type_error_sub():
    """SUB with a string operand must fail."""
    prog = nbc(push_str("hello") + push_int(5) + SUB + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc != 0


def test_type_error_mul():
    prog = nbc(push_int(3) + push_str("x") + MUL + HALT)
    rc, out, err = run_nbc_bytes(prog)
    assert rc != 0


# ---------------------------------------------------------------------------
# Integration: countdown loop
# ---------------------------------------------------------------------------

def test_synth_countdown_5():
    """Countdown from 5 to 1 using JUMP_IF_NZ."""
    # Same structure as trace_loop.nbc but synthesised
    # push 5, (loop:) DUP, PRINTLN, PUSH 1, SUB, DUP, JUMP_IF_NZ loop, POP, HALT
    header = 4
    loop_start = header + 5   # after PUSH_INT 5 (5 bytes)
    # body size: DUP(1) + PRINTLN(1) + PUSH_INT_1(5) + SUB(1) + DUP(1) + JUMP_IF_NZ(3) = 12
    # so POP is at loop_start + 12
    pop_offset = loop_start + 12
    prog = nbc(
        push_int(5) +
        DUP + PRINTLN +
        push_int(1) + SUB +
        DUP + jump_if_nz(loop_start) +
        POP + HALT
    )
    rc, out, err = run_nbc_bytes(prog)
    assert rc == 0, f"non-zero: {err}"
    assert out.strip() == "5\n4\n3\n2\n1"
