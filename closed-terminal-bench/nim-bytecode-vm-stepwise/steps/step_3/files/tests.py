#!/usr/bin/env python3
"""Step 3 visible tests — execution tracing via --trace flag."""

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
    out = "/tmp/nbcvm_s3"
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


# ── Tests ────────────────────────────────────────────────────────────────────

def test_trace_flag_produces_output():
    """Running with --trace creates a non-empty trace file."""
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f:
        trace_path = f.name
    result = run_vm(PROGRAMS / "trace_hello.nbc", trace_path)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    content = Path(trace_path).read_text()
    assert len(content.strip()) > 0, "Trace file is empty"


def test_trace_format_matches_spec():
    """Each trace line matches [NNNN] XXXX: OPNAME ... | stack: [...]."""
    import re
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f:
        trace_path = f.name
    result = run_vm(PROGRAMS / "trace_hello.nbc", trace_path)
    assert result.returncode == 0
    lines = Path(trace_path).read_text().strip().splitlines()
    pattern = re.compile(
        r"^\[\d{4}\] [0-9a-f]{4}: [A-Z_]+.*? \| stack: \[.*\]$"
    )
    for line in lines:
        assert pattern.match(line), f"Line does not match trace format: {line!r}"


def test_trace_instruction_count():
    """trace_hello.nbc trace has exactly 3 instructions (PUSH_STR, PRINTLN, HALT)."""
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f:
        trace_path = f.name
    result = run_vm(PROGRAMS / "trace_hello.nbc", trace_path)
    assert result.returncode == 0
    lines = Path(trace_path).read_text().strip().splitlines()
    assert len(lines) == 3, f"Expected 3 trace lines, got {len(lines)}"


def test_trace_stack_values_correct():
    """Trace output for trace_hello.nbc matches expected trace exactly."""
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f:
        trace_path = f.name
    result = run_vm(PROGRAMS / "trace_hello.nbc", trace_path)
    assert result.returncode == 0
    actual = Path(trace_path).read_text()
    expected = (PROGRAMS / "expected_trace_hello.txt").read_text()
    assert actual == expected, (
        f"Trace mismatch.\nExpected:\n{expected}\nGot:\n{actual}"
    )


def test_trace_deterministic():
    """Running twice with --trace produces identical output."""
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f2:
        p1, p2 = f1.name, f2.name
    run_vm(PROGRAMS / "trace_hello.nbc", p1)
    run_vm(PROGRAMS / "trace_hello.nbc", p2)
    assert Path(p1).read_text() == Path(p2).read_text(), "Trace output not deterministic"


def test_trace_does_not_affect_stdout():
    """stdout is identical with and without --trace."""
    r_no_trace = run_vm(PROGRAMS / "trace_hello.nbc")
    with tempfile.NamedTemporaryFile(suffix=".trace", delete=False) as f:
        trace_path = f.name
    r_trace = run_vm(PROGRAMS / "trace_hello.nbc", trace_path)
    assert r_no_trace.stdout == r_trace.stdout, (
        f"stdout differs.\nWithout trace: {r_no_trace.stdout!r}\n"
        f"With trace: {r_trace.stdout!r}"
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
