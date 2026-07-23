import subprocess
from pathlib import Path

INTERPRETER = "/app/target/release/samscript"
SAMPLES = Path("/app/files/samples")
BOOTSTRAP = Path("/app/files/samscript_bootstrap.sam")


def _run_direct(sam_file: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a .sam program directly with the reference interpreter."""
    return subprocess.run(
        [INTERPRETER, "run", str(sam_file)],
        capture_output=True, text=True, timeout=timeout,
    )


def _run_bootstrap(sam_file: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a .sam program through the bootstrap interpreter."""
    return subprocess.run(
        [INTERPRETER, "run", str(BOOTSTRAP), "--", "run", str(sam_file)],
        capture_output=True, text=True, timeout=timeout,
    )


def test_interpreter_builds():
    """The reference interpreter binary exists and runs."""
    assert Path(INTERPRETER).exists(), (
        f"Interpreter not found at {INTERPRETER}. "
        "It should be pre-built in the container."
    )
    result = subprocess.run(
        [INTERPRETER, "run", str(SAMPLES / "hello.sam")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Interpreter failed:\n{result.stderr}"
    assert "hello world" in result.stdout, f"Unexpected output: {result.stdout}"


def test_bootstrap_exists():
    """The bootstrap interpreter file exists and is non-trivial."""
    assert BOOTSTRAP.exists(), (
        f"Bootstrap file not found at {BOOTSTRAP}. "
        "You must implement /app/files/samscript_bootstrap.sam"
    )
    lines = BOOTSTRAP.read_text().strip().splitlines()
    assert len(lines) >= 50, (
        f"Bootstrap file has only {len(lines)} lines — "
        "a SamScript interpreter needs to be more substantial"
    )


def test_bootstrap_hello():
    """Bootstrap produces 'hello world' for hello.sam."""
    direct = _run_direct(SAMPLES / "hello.sam")
    assert direct.returncode == 0, f"Direct run failed:\n{direct.stderr}"

    boot = _run_bootstrap(SAMPLES / "hello.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"
    assert boot.stdout.strip() == "hello world", (
        f"Expected 'hello world', got: {boot.stdout!r}"
    )


def test_bootstrap_arithmetic():
    """Bootstrap correctly handles arithmetic with string interpolation."""
    boot = _run_bootstrap(SAMPLES / "arithmetic.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "10 + 3 = 13" in lines, f"Missing '10 + 3 = 13' in output:\n{boot.stdout}"
    assert "10 ** 3 = 1000" in lines, f"Missing '10 ** 3 = 1000' in output:\n{boot.stdout}"
    assert "10 % 3 = 1" in lines, f"Missing '10 % 3 = 1' in output:\n{boot.stdout}"


def test_bootstrap_functions_loops():
    """Bootstrap correctly handles functions, loops, factorial, and fibonacci."""
    boot = _run_bootstrap(SAMPLES / "functions_loops.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "5! = 120" in lines, f"Missing '5! = 120' in output:\n{boot.stdout}"
    assert "8! = 40320" in lines, f"Missing '8! = 40320' in output:\n{boot.stdout}"
    assert "fib(10) = 55" in lines, f"Missing 'fib(10) = 55' in output:\n{boot.stdout}"
    assert "fib(15) = 610" in lines, f"Missing 'fib(15) = 610' in output:\n{boot.stdout}"


def test_bootstrap_string_ops():
    """Bootstrap correctly handles string operations and concatenation."""
    boot = _run_bootstrap(SAMPLES / "string_ops.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "range: 1, 2, 3, 4, 5" in lines, f"Missing range output:\n{boot.stdout}"
    assert "Hello WASM" in lines, f"Missing 'Hello WASM' in output:\n{boot.stdout}"
    assert "repeat(abc, 3) = abcabcabc" in lines, f"Missing repeat output:\n{boot.stdout}"


def test_bootstrap_logic():
    """Bootstrap correctly handles booleans, comparisons, and conditionals."""
    boot = _run_bootstrap(SAMPLES / "logic.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "classify(5) = positive" in lines, f"Missing classify output:\n{boot.stdout}"
    assert "classify(-3) = negative" in lines, f"Missing classify output:\n{boot.stdout}"
    assert "classify(0) = zero" in lines, f"Missing classify output:\n{boot.stdout}"
    assert "not true = false" in lines, f"Missing not output:\n{boot.stdout}"


def test_bootstrap_deterministic():
    """Running the same program through bootstrap twice gives identical output."""
    out1 = _run_bootstrap(SAMPLES / "hello.sam")
    out2 = _run_bootstrap(SAMPLES / "hello.sam")
    assert out1.returncode == 0, f"First run failed:\n{out1.stderr}"
    assert out2.returncode == 0, f"Second run failed:\n{out2.stderr}"
    assert out1.stdout == out2.stdout, (
        f"Non-deterministic output:\nRun 1: {out1.stdout!r}\nRun 2: {out2.stdout!r}"
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
