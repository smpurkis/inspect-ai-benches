#!/usr/bin/env python3
"""Step 2 hidden tests — deeper validation of control flow and I/O opcodes."""

import subprocess
import sys
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
    out = "/tmp/nbcvm_s2h"
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


# ── Tests ────────────────────────────────────────────────────────────────────

def test_hidden_nested_branches():
    """nested_branch.nbc navigates two levels of if/else correctly."""
    result = run_vm(PROGRAMS / "nested_branch.nbc")
    expected = (PROGRAMS / "expected_nested_branch.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_hidden_loop_100_iterations():
    """loop_100.nbc computes sum(1..100) = 5050 via JNZ loop."""
    result = run_vm(PROGRAMS / "loop_100.nbc")
    expected = (PROGRAMS / "expected_loop_100.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_hidden_file_read_opcode():
    """file_read.nbc writes then reads a file, printing the content."""
    result = run_vm(PROGRAMS / "file_read.nbc")
    expected = (PROGRAMS / "expected_file_read.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_hidden_division_by_zero():
    """Division by zero causes a nonzero exit code."""
    result = run_vm(PROGRAMS / "div_zero.nbc")
    assert result.returncode != 0, "Expected nonzero exit for division by zero"


def test_hidden_jump_out_of_bounds():
    """Jumping to an out-of-bounds offset causes a nonzero exit code."""
    result = run_vm(PROGRAMS / "jump_oob.nbc")
    assert result.returncode != 0, "Expected nonzero exit for jump out of bounds"


def test_hidden_mixed_types_on_stack():
    """type_mismatch.nbc (ADD on string + int) causes error exit."""
    result = run_vm(PROGRAMS / "type_mismatch.nbc")
    assert result.returncode != 0, "Expected nonzero exit for type mismatch"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
