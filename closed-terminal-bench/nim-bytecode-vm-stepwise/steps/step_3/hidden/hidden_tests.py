#!/usr/bin/env python3
"""Step 3 hidden tests — deeper trace validation with branches, loops, errors."""

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
    out = "/tmp/nbcvm_s3h"
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


def run_vm(nbc_file, trace_path=None):
    vm = compile_vm()
    cmd = [vm, str(nbc_file)]
    if trace_path:
        cmd.extend(["--trace", str(trace_path)])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def run_traced(nbc_file) -> tuple[subprocess.CompletedProcess, str]:
    """Run with trace, return (result, trace_content)."""
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f:
        tp = f.name
    result = run_vm(nbc_file, tp)
    content = Path(tp).read_text()
    return result, content


# ── Tests ────────────────────────────────────────────────────────────────────

def test_hidden_trace_branch_program():
    """trace_branch.nbc trace matches expected trace (branch taken/not taken)."""
    result, trace = run_traced(PROGRAMS / "trace_branch.nbc")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    expected = (PROGRAMS / "expected_trace_branch.txt").read_text()
    assert trace == expected, (
        f"Trace mismatch.\nExpected:\n{expected}\nGot:\n{trace}"
    )


def test_hidden_trace_loop_program():
    """trace_loop.nbc trace matches expected trace for countdown-from-3."""
    result, trace = run_traced(PROGRAMS / "trace_loop.nbc")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    expected = (PROGRAMS / "expected_trace_loop.txt").read_text()
    assert trace == expected, (
        f"Trace mismatch.\nExpected:\n{expected}\nGot:\n{trace}"
    )


def test_hidden_trace_byte_identical():
    """Running trace twice on trace_loop.nbc produces byte-identical output."""
    _, trace1 = run_traced(PROGRAMS / "trace_loop.nbc")
    _, trace2 = run_traced(PROGRAMS / "trace_loop.nbc")
    assert trace1 == trace2, "Trace output not byte-identical across runs"


def test_hidden_trace_error_program():
    """trace_error.nbc (div-by-zero) records instructions before the error."""
    result, trace = run_traced(PROGRAMS / "trace_error.nbc")
    assert result.returncode != 0, "Expected nonzero exit for div-by-zero"
    expected = (PROGRAMS / "expected_trace_error.txt").read_text()
    assert trace == expected, (
        f"Trace mismatch.\nExpected:\n{expected}\nGot:\n{trace}"
    )


def test_hidden_trace_large_program():
    """trace_large.nbc (countdown from 10) produces correct line count and format."""
    result, trace = run_traced(PROGRAMS / "trace_large.nbc")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    expected = (PROGRAMS / "expected_trace_large.txt").read_text()
    assert trace == expected, (
        f"Trace mismatch (large program).\n"
        f"Expected {len(expected.splitlines())} lines, got {len(trace.splitlines())}"
    )


def test_hidden_trace_file_io_program():
    """trace_fileio.nbc (FWRITE + FREAD) trace matches expected."""
    result, trace = run_traced(PROGRAMS / "trace_fileio.nbc")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    expected = (PROGRAMS / "expected_trace_fileio.txt").read_text()
    assert trace == expected, (
        f"Trace mismatch.\nExpected:\n{expected}\nGot:\n{trace}"
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
