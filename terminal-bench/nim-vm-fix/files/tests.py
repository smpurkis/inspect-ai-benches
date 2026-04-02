#!/usr/bin/env python3
"""Visible tests — fix the broken Nim bytecode VM."""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC_DIR = BASE / "src"
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


def run_vm(nbc_file, extra_args=None):
    vm = compile_vm()
    cmd = [vm, str(nbc_file)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_binary_builds():
    """The Nim source compiles without errors."""
    compile_vm()


def test_hello_program_runs():
    """hello.nbc runs and exits with code 0."""
    result = run_vm(PROGRAMS / "hello.nbc")
    assert result.returncode == 0, f"exit code {result.returncode}\nstderr: {result.stderr}"


def test_hello_output_matches():
    """hello.nbc output matches expected_hello.txt."""
    result = run_vm(PROGRAMS / "hello.nbc")
    expected = (PROGRAMS / "expected_hello.txt").read_text()
    assert result.stdout == expected, (
        f"Output mismatch.\n  Got:    {result.stdout!r}\n  Expect: {expected!r}"
    )


def test_arithmetic_program():
    """arithmetic.nbc computes 2+3*4=14 correctly."""
    result = run_vm(PROGRAMS / "arithmetic.nbc")
    expected = (PROGRAMS / "expected_arithmetic.txt").read_text()
    assert result.returncode == 0, f"exit code {result.returncode}\nstderr: {result.stderr}"
    assert result.stdout == expected, (
        f"Output mismatch.\n  Got:    {result.stdout!r}\n  Expect: {expected!r}"
    )


def test_deterministic_execution():
    """Running the same program twice produces identical output."""
    r1 = run_vm(PROGRAMS / "hello.nbc")
    r2 = run_vm(PROGRAMS / "hello.nbc")
    assert r1.stdout == r2.stdout, "Non-deterministic output detected"


def test_exit_code_zero_on_success():
    """Both test programs exit with code 0."""
    for prog in ["hello.nbc", "arithmetic.nbc"]:
        result = run_vm(PROGRAMS / prog)
        assert result.returncode == 0, (
            f"{prog} exited with {result.returncode}\nstderr: {result.stderr}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
