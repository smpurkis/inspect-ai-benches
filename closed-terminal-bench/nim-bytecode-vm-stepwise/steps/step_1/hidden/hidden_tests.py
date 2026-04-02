#!/usr/bin/env python3
"""Step 1 hidden tests — additional validation of the fixed VM."""

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC_DIR = Path("/app/step_1/files/src")
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


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
