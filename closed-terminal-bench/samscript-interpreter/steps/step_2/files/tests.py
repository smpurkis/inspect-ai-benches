import subprocess
import sys
from pathlib import Path

BINARY = "/app/target/release/samscript"
SAMPLES = Path("/app/step_2/files/samples")


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


def test_list_operations():
    """List creation, indexing, mutation, and len work."""
    _build()
    result = _run_interpreted(SAMPLES / "lists.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert "length: 5" in lines
    assert "first: 1" in lines
    assert "last: 5" in lines
    assert "after append length: 6" in lines
    assert "modified first: 10" in lines
    assert "sum: 30" in lines  # 10+2+3+4+5+6 = 30


def test_dict_operations():
    """Dict creation, access, mutation work."""
    _build()
    result = _run_interpreted(SAMPLES / "dicts.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert "name: Alice" in lines
    assert "age: 30" in lines
    assert "length: 3" in lines
    assert "updated age: 31" in lines
    assert "email: alice@example.com" in lines
    assert "new length: 4" in lines


def test_module_import():
    """from math import sqrt resolves correctly."""
    _build()
    result = _run_interpreted(SAMPLES / "imports.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert "sqrt(16) = 4" in lines
    assert "abs(-42) = 42" in lines
    assert "abs(7) = 7" in lines
    # sqrt(2) should be approximately 1.414...
    sqrt2_line = [l for l in lines if "sqrt(2)" in l]
    assert len(sqrt2_line) == 1, f"expected one sqrt(2) line, got {sqrt2_line}"
    val = sqrt2_line[0].split("~= ")[1]
    assert abs(float(val) - 1.41421356) < 0.001, f"sqrt(2) too far off: {val}"


def test_nested_containers():
    """List of dicts, dict of lists, nested lists work."""
    _build()
    result = _run_interpreted(SAMPLES / "nested_containers.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert "Alice is 30" in lines
    assert "Bob is 25" in lines
    assert "Charlie is 35" in lines
    assert "math scores: 3" in lines
    assert "first math score: 90" in lines
    assert "matrix[1][2] = 6" in lines


def test_circular_import_error():
    """Circular imports produce a clear error, not a hang."""
    _build()
    # Write a test program that triggers circular import
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sam", dir=str(SAMPLES / "modules"), delete=False
    ) as f:
        f.write('from circular_a import foo\n\nfn main() {\n    print(foo())\n}\n')
        test_file = f.name

    try:
        result = subprocess.run(
            [BINARY, "run", test_file],
            capture_output=True,
            text=True,
            timeout=10,  # should fail fast, not hang
        )
        assert result.returncode != 0, "circular import should produce an error"
        stderr = result.stderr.lower()
        assert any(word in stderr for word in ["circular", "cycle", "recursive import"]), (
            f"error should mention circular/cycle:\n{result.stderr}"
        )
    finally:
        Path(test_file).unlink(missing_ok=True)


def test_all_builtins_available():
    """print, input, len, type, str, num, assert all work."""
    _build()
    result = _run_interpreted(SAMPLES / "builtins.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert "testing builtins" in lines
    assert "len of 'hello': 5" in lines
    assert "len of [1,2,3]: 3" in lines
    assert "type(42): number" in lines
    assert "type('hi'): string" in lines
    assert "type(true): bool" in lines
    assert "type(none): none" in lines
    assert "type([]): list" in lines
    assert "type({}): dict" in lines
    assert "str(42) = 42" in lines
    assert "num('3.14') = 3.14" in lines
    assert "all assertions passed" in lines


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
