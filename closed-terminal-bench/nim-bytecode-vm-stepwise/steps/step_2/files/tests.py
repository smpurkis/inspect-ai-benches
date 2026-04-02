#!/usr/bin/env python3
"""Step 2 visible tests — control flow, comparisons, and file I/O opcodes."""

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
    out = "/tmp/nbcvm_s2"
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

def test_conditional_jump():
    """JZ correctly jumps when the stack top is zero."""
    # Build inline: PUSH 0, JZ to "taken" label, PUSH "no", PRINTLN, JMP end,
    #               "taken": PUSH "taken", PRINTLN, HALT
    prog = b"NBC\x01"
    prog += b"\x01" + struct.pack("<i", 0)            # PUSH_INT 0
    prog += b"\x11" + struct.pack("<H", 21)           # JZ 21
    prog += b"\x02" + struct.pack("<H", 2) + b"no"    # PUSH_STR "no"
    prog += b"\x08"                                    # PRINTLN
    prog += b"\x10" + struct.pack("<H", 30)           # JMP 30
    prog += b"\x02" + struct.pack("<H", 5) + b"taken" # PUSH_STR "taken"
    prog += b"\x08"                                    # PRINTLN
    prog += b"\xff"                                    # HALT
    result = run_vm_bytes(prog)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout.strip() == "taken", f"Got: {result.stdout!r}"


def test_loop_via_jump():
    """loop_sum.nbc computes sum(1..5) = 15 using JNZ loop."""
    result = run_vm(PROGRAMS / "loop_sum.nbc")
    expected = (PROGRAMS / "expected_loop_sum.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_comparison_operators():
    """comparisons.nbc tests CMP_LT, CMP_EQ, CMP_GT for (3,5)."""
    result = run_vm(PROGRAMS / "comparisons.nbc")
    expected = (PROGRAMS / "expected_comparisons.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


def test_file_write_opcode():
    """file_write.nbc writes 'hello from nbc' to /tmp/nbc_output.txt."""
    out_path = Path("/tmp/nbc_output.txt")
    if out_path.exists():
        out_path.unlink()
    result = run_vm(PROGRAMS / "file_write.nbc")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert out_path.exists(), "FWRITE did not create the file"
    assert out_path.read_text() == "hello from nbc"


def test_malformed_bytecode_typed_error():
    """ADD on string + integer causes a type-error exit."""
    prog = b"NBC\x01"
    prog += b"\x02" + struct.pack("<H", 5) + b"hello"  # PUSH_STR "hello"
    prog += b"\x01" + struct.pack("<i", 42)             # PUSH_INT 42
    prog += b"\x03"                                      # ADD
    prog += b"\xff"                                      # HALT
    result = run_vm_bytes(prog)
    assert result.returncode != 0, "Expected nonzero exit for type mismatch"


def test_branch_program_output():
    """branch_simple.nbc prints 'yes' (nonzero condition, JZ not taken)."""
    result = run_vm(PROGRAMS / "branch_simple.nbc")
    expected = (PROGRAMS / "expected_branch_simple.txt").read_text()
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    assert result.stdout == expected


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
