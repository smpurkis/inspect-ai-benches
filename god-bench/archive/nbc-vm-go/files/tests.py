"""Visible tests for nbc-vm-go: NBC bytecode VM implemented in Go.

The agent must:
  go build -o /app/nbcvm /app/files/
  /app/nbcvm <program.nbc>
"""

import subprocess
import os
import pytest

FILES = "/app/files"
VM = "/app/nbcvm"


def run_nbc(prog, *, input_data=None, timeout=10):
    """Run the VM on a .nbc file, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [VM, os.path.join(FILES, prog)],
        capture_output=True, text=True, timeout=timeout,
        input=input_data,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def test_build():
    """The Go source must compile to /app/nbcvm."""
    r = subprocess.run(
        ["go", "build", "-o", VM, FILES + "/"],
        capture_output=True, text=True, cwd="/app"
    )
    assert r.returncode == 0, f"go build failed:\n{r.stderr}"
    assert os.path.isfile(VM), "/app/nbcvm not created after build"
    assert os.access(VM, os.X_OK), "/app/nbcvm not executable"


# ---------------------------------------------------------------------------
# Basic output
# ---------------------------------------------------------------------------

def test_hello():
    rc, out, err = run_nbc("hello.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "Hello, World!"


def test_empty():
    """empty.nbc is just HALT — no output, zero exit."""
    rc, out, err = run_nbc("empty.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out == ""


def test_arithmetic():
    """2 + 3*4 = 14"""
    rc, out, err = run_nbc("arithmetic.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "14"


def test_nested_arithmetic():
    """(10-3)*2+1 = 15"""
    rc, out, err = run_nbc("nested_arithmetic.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "15"


def test_strings():
    """PRINT 'foo' (no newline) then PRINTLN 'bar'."""
    rc, out, err = run_nbc("strings.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out == "foobar\n"


def test_fibonacci():
    """Pre-computed Fibonacci sequence 0..34."""
    rc, out, err = run_nbc("fibonacci.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    expected = "0\n1\n1\n2\n3\n5\n8\n13\n21\n34"
    assert out.strip() == expected


# ---------------------------------------------------------------------------
# Comparisons and branching
# ---------------------------------------------------------------------------

def test_comparisons():
    """LT, GT, EQ: 3<5→1, 3>5→0, 3==5→0."""
    rc, out, err = run_nbc("comparisons.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    lines = out.strip().splitlines()
    assert lines == ["1", "0", "0"], f"got {lines!r}"


def test_branch_simple():
    """PUSH 1, JUMP_IF_Z (not taken) → prints 'yes'."""
    rc, out, err = run_nbc("branch_simple.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "yes"


def test_nested_branch():
    """Outer=1 (not zero, skip outer-no), inner=0 (zero, jump to inner-no)."""
    rc, out, err = run_nbc("nested_branch.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "inner-no"


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------

def test_loop_sum():
    """Sum 1+2+3+4+5 = 15."""
    rc, out, err = run_nbc("loop_sum.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "15"


def test_loop_100():
    """Sum 1..100 = 5050."""
    rc, out, err = run_nbc("loop_100.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "5050"


# ---------------------------------------------------------------------------
# Trace programs (execution order / instruction coverage)
# ---------------------------------------------------------------------------

def test_trace_hello():
    rc, out, err = run_nbc("trace_hello.nbc")
    assert rc == 0
    assert out.strip() == "Hello, World!"


def test_trace_branch():
    """Same as branch_simple: prints 'yes'."""
    rc, out, err = run_nbc("trace_branch.nbc")
    assert rc == 0
    assert out.strip() == "yes"


def test_trace_loop():
    """Counts 3, 2, 1 using DUP/JUMP_IF_NZ."""
    rc, out, err = run_nbc("trace_loop.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "3\n2\n1"


def test_trace_large():
    """Counts 10, 9, ..., 1."""
    rc, out, err = run_nbc("trace_large.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    expected = "\n".join(str(i) for i in range(10, 0, -1))
    assert out.strip() == expected


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def test_file_write():
    """FILE_WRITE pushes string then writes to /tmp/nbc_output.txt."""
    # Clean up first
    out_path = "/tmp/nbc_output.txt"
    if os.path.exists(out_path):
        os.remove(out_path)
    rc, out, err = run_nbc("file_write.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert os.path.isfile(out_path), "file not created"
    content = open(out_path).read()
    assert content == "hello from nbc", f"wrong content: {content!r}"


def test_file_read():
    """FILE_WRITE then FILE_READ: prints 'test content'."""
    rc, out, err = run_nbc("file_read.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "test content"


def test_trace_fileio():
    """Write 'traced data' then read it back and println."""
    rc, out, err = run_nbc("trace_fileio.nbc")
    assert rc == 0, f"non-zero exit: {err}"
    assert out.strip() == "traced data"


# ---------------------------------------------------------------------------
# Error conditions (VM must exit non-zero)
# ---------------------------------------------------------------------------

def test_div_zero():
    rc, out, err = run_nbc("div_zero.nbc")
    assert rc != 0, "expected non-zero exit for div-by-zero"
    assert err.strip() != "", "expected error message on stderr"


def test_jump_oob():
    rc, out, err = run_nbc("jump_oob.nbc")
    assert rc != 0, "expected non-zero exit for out-of-bounds jump"
    assert err.strip() != "", "expected error message on stderr"


def test_type_mismatch():
    """ADD with string and int must fail."""
    rc, out, err = run_nbc("type_mismatch.nbc")
    assert rc != 0, "expected non-zero exit for type mismatch"
    assert err.strip() != "", "expected error message on stderr"


def test_trace_error():
    """Same as div_zero — must exit non-zero."""
    rc, out, err = run_nbc("trace_error.nbc")
    assert rc != 0, "expected non-zero exit"
