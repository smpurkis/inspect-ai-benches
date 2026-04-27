#!/usr/bin/env python3
"""Hidden tests — additional validation of the fixed VM."""

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC_DIR = Path("/app/files/src")
PROGRAMS = BASE / "programs"

_vm_cache: str | None = None
_compile_err: str | None = None


def compile_vm() -> str:
    global _vm_cache, _compile_err
    if _vm_cache is not None:
        return _vm_cache
    if _compile_err is not None:
        raise AssertionError(_compile_err)
    out = "/tmp/nbcvm"
    result = subprocess.run(
        ["nim", "compile", "-d:release", "--hints:off",
         "--out:" + out, str(SRC_DIR / "main.nim")],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        _compile_err = f"Compilation failed:\n{result.stderr}"
        raise AssertionError(_compile_err)
    _vm_cache = out
    return out


def run_vm(nbc_file):
    vm = compile_vm()
    return subprocess.run(
        [vm, str(nbc_file)], capture_output=True, text=True, timeout=30,
    )


def run_vm_bytes(data: bytes):
    """Write bytecode to a temp file and run it."""
    with tempfile.NamedTemporaryFile(suffix=".nbc", delete=False) as f:
        f.write(data)
        f.flush()
        return run_vm(f.name)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_hidden_fibonacci_program():
    """fibonacci.nbc prints the first 10 Fibonacci numbers."""
    result = run_vm(PROGRAMS / "fibonacci.nbc")
    expected = (PROGRAMS / "expected_fibonacci.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_hidden_stack_underflow_error():
    """Popping from an empty stack exits with nonzero code."""
    prog = b"NBC\x01" + b"\x0a" + b"\xff"  # POP, HALT
    result = run_vm_bytes(prog)
    assert result.returncode != 0, "Expected nonzero exit for stack underflow"


def test_hidden_invalid_opcode_rejected():
    """An unknown opcode byte causes an error exit."""
    prog = b"NBC\x01" + b"\xfe" + b"\xff"  # 0xFE is not a valid opcode
    result = run_vm_bytes(prog)
    assert result.returncode != 0, "Expected nonzero exit for invalid opcode"


def test_hidden_nested_arithmetic():
    """nested_arithmetic.nbc computes (10-3)*2+1 = 15."""
    result = run_vm(PROGRAMS / "nested_arithmetic.nbc")
    expected = (PROGRAMS / "expected_nested_arithmetic.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_hidden_string_operations():
    """strings.nbc prints 'foobar' using PRINT and PRINTLN."""
    result = run_vm(PROGRAMS / "strings.nbc")
    expected = (PROGRAMS / "expected_strings.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_hidden_empty_program():
    """empty.nbc (just HALT) produces no output and exits 0."""
    result = run_vm(PROGRAMS / "empty.nbc")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == "", f"Expected no output, got: {result.stdout!r}"


# ── Synthesized bytecode tests ────────────────────────────────────────────────

def _push_int(n: int) -> bytes:
    """Encode a PUSH_INT instruction (opcode 0x01 + 4-byte LE int32)."""
    return b"\x01" + struct.pack("<i", n)


def test_hidden_sub_operand_order():
    """PUSH 10; PUSH 3; SUB; PRINTLN should print 7 (not -7).

    SUB must pop b then a and compute a - b (i.e. 10 - 3 = 7).
    """
    prog = b"NBC\x01" + _push_int(10) + _push_int(3) + b"\x04" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "7", \
        f"Expected '7' from (10 - 3), got: {result.stdout.strip()!r}"


def test_hidden_div_operand_order():
    """PUSH 10; PUSH 2; DIV; PRINTLN should print 5 (not 0).

    DIV must pop b then a and compute a / b (i.e. 10 / 2 = 5).
    """
    prog = b"NBC\x01" + _push_int(10) + _push_int(2) + b"\x06" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "5", \
        f"Expected '5' from (10 / 2), got: {result.stdout.strip()!r}"


def test_hidden_invalid_magic_header():
    """Bytecode not starting with 'NBC\\x01' must exit with nonzero code."""
    prog = b"BAD\x01" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode != 0, \
        "Expected nonzero exit for invalid magic header 'BAD\\x01'"


def test_hidden_print_integer_no_newline():
    """PUSH 42; PRINT (0x07) should print '42' without a trailing newline."""
    prog = b"NBC\x01" + _push_int(42) + b"\x07" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == "42", \
        f"Expected '42' (no newline) from PRINT, got: {result.stdout!r}"


def test_hidden_add_correctness():
    """PUSH 15; PUSH 27; ADD; PRINTLN should print 42."""
    prog = b"NBC\x01" + _push_int(15) + _push_int(27) + b"\x03" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "42", \
        f"Expected '42' from (15 + 27), got: {result.stdout.strip()!r}"


def test_hidden_mul_correctness():
    """PUSH 6; PUSH 7; MUL; PRINTLN should print 42."""
    prog = b"NBC\x01" + _push_int(6) + _push_int(7) + b"\x05" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "42", \
        f"Expected '42' from (6 * 7), got: {result.stdout.strip()!r}"


def test_hidden_multiple_println():
    """Multiple PRINTLN calls must each be on their own line."""
    prog = (b"NBC\x01"
            + _push_int(1) + b"\x08"   # PRINTLN 1
            + _push_int(2) + b"\x08"   # PRINTLN 2
            + _push_int(3) + b"\x08"   # PRINTLN 3
            + b"\xff")
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == "1\n2\n3\n", \
        f"Expected '1\\n2\\n3\\n', got: {result.stdout!r}"


def test_hidden_large_integer():
    """PUSH 100000; PRINTLN should print '100000' (tests int32 LE byte order)."""
    prog = b"NBC\x01" + _push_int(100000) + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "100000", \
        f"Expected '100000', got: {result.stdout.strip()!r}"


def test_hidden_over_distinct_from_dup():
    """PUSH 10; PUSH 20; OVER; PRINTLN should print '10' (second element, not top).

    OVER must copy the second stack element, not duplicate the top.
    """
    # OVER = 0x0D
    prog = b"NBC\x01" + _push_int(10) + _push_int(20) + b"\x0d" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "10", \
        f"Expected '10' from OVER (second element), got: {result.stdout.strip()!r}"


def test_hidden_negative_integer():
    """PUSH -42; PRINTLN should print '-42' (tests signed int32 handling)."""
    prog = b"NBC\x01" + _push_int(-42) + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "-42", \
        f"Expected '-42', got: {result.stdout.strip()!r}"


def test_hidden_sub_negative_result():
    """PUSH 3; PUSH 10; SUB; PRINTLN should print '-7'.

    Tests that negative results from arithmetic are preserved correctly.
    """
    prog = b"NBC\x01" + _push_int(3) + _push_int(10) + b"\x04" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "-7", \
        f"Expected '-7' from (3 - 10), got: {result.stdout.strip()!r}"


def test_hidden_wrong_version_byte():
    """NBC header with wrong version byte (0x02) must be rejected."""
    prog = b"NBC\x02" + b"\xff"  # correct magic, wrong version
    result = run_vm_bytes(prog)
    assert result.returncode != 0, \
        "Expected nonzero exit for wrong NBC version byte (0x02)"


def test_hidden_dup_on_multi_element_stack():
    """PUSH 10; PUSH 20; DUP; PRINTLN should print '20' (top), not '10' (bottom).

    DUP must copy the top of stack, not the bottom.
    """
    prog = b"NBC\x01" + _push_int(10) + _push_int(20) + b"\x09" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "20", \
        f"Expected '20' from DUP (top of stack), got: {result.stdout.strip()!r}"


def test_hidden_mul_large_product():
    """PUSH 1000; PUSH 1000; MUL; PRINTLN should print '1000000'.

    MUL must produce full int32 results, not truncated to int16.
    """
    prog = b"NBC\x01" + _push_int(1000) + _push_int(1000) + b"\x05" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "1000000", \
        f"Expected '1000000' from (1000 * 1000), got: {result.stdout.strip()!r}"


def test_hidden_swap_correctness():
    """PUSH 5; PUSH 10; SWAP; PRINTLN should print '5' (originally second, now on top).

    SWAP must actually exchange the top two elements.
    """
    # SWAP = 0x0C
    prog = b"NBC\x01" + _push_int(5) + _push_int(10) + b"\x0c" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "5", \
        f"Expected '5' after SWAP, got: {result.stdout.strip()!r}"


def test_hidden_push_neg_one():
    """PUSH -1; PRINTLN should print '-1' (tests signed int32 decoding)."""
    prog = b"NBC\x01" + _push_int(-1) + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "-1", \
        f"Expected '-1', got: {result.stdout.strip()!r}"


def test_hidden_push_neg_thousand():
    """PUSH -1000; PRINTLN should print '-1000'."""
    prog = b"NBC\x01" + _push_int(-1000) + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "-1000", \
        f"Expected '-1000', got: {result.stdout.strip()!r}"


def test_hidden_neg_add_to_zero():
    """PUSH -5; PUSH 5; ADD; PRINTLN should print '0'.

    Tests that negative values decoded from bytecode participate in arithmetic correctly.
    """
    prog = b"NBC\x01" + _push_int(-5) + _push_int(5) + b"\x03" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "0", \
        f"Expected '0' from (-5 + 5), got: {result.stdout.strip()!r}"


def test_hidden_neg_mul():
    """PUSH -3; PUSH 7; MUL; PRINTLN should print '-21'."""
    prog = b"NBC\x01" + _push_int(-3) + _push_int(7) + b"\x05" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "-21", \
        f"Expected '-21' from (-3 * 7), got: {result.stdout.strip()!r}"


def test_hidden_neg_div():
    """PUSH -20; PUSH 4; DIV; PRINTLN should print '-5'."""
    prog = b"NBC\x01" + _push_int(-20) + _push_int(4) + b"\x06" + b"\x08" + b"\xff"
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "-5", \
        f"Expected '-5' from (-20 / 4), got: {result.stdout.strip()!r}"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
