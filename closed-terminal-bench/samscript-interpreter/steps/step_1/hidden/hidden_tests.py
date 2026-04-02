import subprocess
import sys
from pathlib import Path

BINARY = "/app/target/release/samscript"
HIDDEN_SAMPLES = Path("/app/step_1/hidden/samples")


def _build():
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=600,
    )
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"


def _run_interpreted(sam_file: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BINARY, "run", str(sam_file)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_compiled(sam_file: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    out_bin = f"/tmp/{sam_file.stem}_compiled"
    comp = subprocess.run(
        [BINARY, "compile", str(sam_file), "-o", out_bin],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert comp.returncode == 0, (
        f"compilation failed for {sam_file.name}:\n{comp.stderr[-2000:]}"
    )
    return subprocess.run(
        [out_bin],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_hidden_nested_functions():
    """Nested function calls with defaults produce correct output."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "nested_functions.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "14", f"expected 14, got {lines[0]}"      # add_then_double(3,4) = double(7) = 14
    assert lines[1] == "30", f"expected 30, got {lines[1]}"      # add_then_double(10,5) = double(15) = 30
    assert lines[2] == "Hello, Alice!"                            # make_greeting("Alice")
    assert lines[3] == "Hi, Bob!"                                 # make_greeting("Bob", "Hi")
    assert lines[4] == "nested: 12"                               # double(add_then_double(1,2)) = double(6) = 12


def test_hidden_variable_scoping():
    """Block scoping rules enforced correctly."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "scoping.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "outer x = 10"
    assert lines[1] == "inner x = 20"
    assert lines[2] == "inner y = 30"
    assert lines[3] == "outer x after block = 10"
    assert lines[4] == "outer counter = 0"


def test_hidden_const_reassignment_error():
    """Assigning to a const variable produces a clear error."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "const_error.sam")
    assert result.returncode != 0, "expected non-zero exit for const reassignment"
    stderr = result.stderr.lower()
    # Must mention const or immutable or reassign
    assert any(word in stderr for word in ["const", "immutable", "reassign", "cannot assign"]), (
        f"error message should mention const/immutable/reassign:\n{result.stderr}"
    )


def test_hidden_undeclared_variable_error():
    """Bare assignment to an undeclared variable is an error."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "undeclared_error.sam")
    assert result.returncode != 0, "expected non-zero exit for undeclared variable"
    stderr = result.stderr.lower()
    assert any(word in stderr for word in ["undeclared", "undefined", "not defined", "not declared"]), (
        f"error message should mention undeclared/undefined:\n{result.stderr}"
    )


def test_hidden_no_main_error():
    """Program without main() produces a descriptive error."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "no_main_error.sam")
    assert result.returncode != 0, "expected non-zero exit when no main function"
    stderr = result.stderr.lower()
    assert "main" in stderr, (
        f"error message should mention 'main':\n{result.stderr}"
    )


def test_hidden_complex_program_parity():
    """Complex 50-line program produces identical output in both modes."""
    _build()
    interp = _run_interpreted(HIDDEN_SAMPLES / "complex_program.sam")
    assert interp.returncode == 0, f"interpreter failed:\n{interp.stderr}"

    compiled = _run_compiled(HIDDEN_SAMPLES / "complex_program.sam")
    assert compiled.returncode == 0, f"compiled binary failed:\n{compiled.stderr}"

    assert interp.stdout == compiled.stdout, (
        f"output mismatch for complex_program.sam:\n"
        f"  interpreter:\n{interp.stdout}\n"
        f"  compiled:\n{compiled.stdout}"
    )

    # Also verify some specific expected outputs
    lines = interp.stdout.strip().splitlines()
    assert "abs(-5) = 5" in lines
    assert "abs(3) = 3" in lines
    assert "clamp(15, 0, 10) = 10" in lines
    assert "fib(0) = 0" in lines
    assert "fib(10) = 55" in lines
    assert "2 ** 10 = 1024" in lines
    assert "true and false = false" in lines
    assert "not true = false" in lines
    assert "LIMIT = 5" in lines


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
