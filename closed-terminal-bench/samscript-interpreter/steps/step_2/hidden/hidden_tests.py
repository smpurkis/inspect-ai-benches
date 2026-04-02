import subprocess
import sys
from pathlib import Path

BINARY = "/app/target/release/samscript"
HIDDEN_SAMPLES = Path("/app/step_2/hidden/samples")


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


def test_hidden_list_out_of_bounds():
    """Accessing list out of bounds produces a clear error."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "list_oob.sam")
    assert result.returncode != 0, "expected error for out-of-bounds access"
    stderr = result.stderr.lower()
    assert any(word in stderr for word in ["index", "out of bounds", "out of range", "range"]), (
        f"error should mention index/bounds:\n{result.stderr}"
    )


def test_hidden_dict_missing_key():
    """Accessing missing dict key produces a clear error."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "dict_missing.sam")
    assert result.returncode != 0, "expected error for missing dict key"
    stderr = result.stderr.lower()
    assert any(word in stderr for word in ["key", "not found", "missing", "does not exist"]), (
        f"error should mention key/missing:\n{result.stderr}"
    )


def test_hidden_transitive_imports():
    """A imports B imports C works correctly (transitive resolution)."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "transitive" / "a.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    # BASE() returns 42, get_value() returns 42+10=52, compute() returns 52*2=104
    assert lines[0] == "result: 104", f"expected 'result: 104', got '{lines[0]}'"


def test_hidden_empty_containers():
    """Operations on [] and {} behave correctly."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "empty_containers.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert "empty list len: 0" in lines
    assert "empty dict len: 0" in lines
    assert "empty list type: list" in lines
    assert "empty dict type: dict" in lines
    assert "after add: 1" in lines
    assert "first item: first" in lines
    assert "after add dict: 1" in lines
    assert "dict value: value" in lines


def test_hidden_error_stack_trace():
    """Errors show file:line stack trace."""
    _build()
    result = _run_interpreted(HIDDEN_SAMPLES / "error_trace.sam")
    assert result.returncode != 0, "expected error for division by zero"
    stderr = result.stderr.lower()
    # Must contain stack trace with function names
    assert "stack trace" in stderr or "trace" in stderr, (
        f"error should include a stack trace:\n{result.stderr}"
    )
    assert "inner" in stderr, (
        f"stack trace should mention 'inner' function:\n{result.stderr}"
    )
    assert "main" in stderr, (
        f"stack trace should mention 'main' function:\n{result.stderr}"
    )


def test_hidden_compound_type_parity():
    """Complex program with lists/dicts produces identical output in both modes."""
    _build()
    interp = _run_interpreted(HIDDEN_SAMPLES / "compound_parity.sam")
    assert interp.returncode == 0, f"interpreter failed:\n{interp.stderr}"

    compiled = _run_compiled(HIDDEN_SAMPLES / "compound_parity.sam")
    assert compiled.returncode == 0, f"compiled binary failed:\n{compiled.stderr}"

    assert interp.stdout == compiled.stdout, (
        f"output mismatch for compound_parity.sam:\n"
        f"  interpreter:\n{interp.stdout}\n"
        f"  compiled:\n{compiled.stdout}"
    )

    # Verify expected outputs
    lines = interp.stdout.strip().splitlines()
    assert "alpha: count=3, sum=60" in lines
    assert "beta: count=4, sum=80" in lines
    assert "gamma: count=1, sum=100" in lines
    assert "flat length: 6" in lines
    assert "flat sum: 21" in lines


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
