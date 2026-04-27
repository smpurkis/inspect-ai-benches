import subprocess
import tempfile
from pathlib import Path

INTERPRETER = "/app/target/release/samscript"
SAMPLES = Path("/app/files/samples")
HIDDEN_SAMPLES = Path("/app/hidden/samples")
BOOTSTRAP = Path("/app/samscript_bootstrap.sam")
PRISTINE_SRC = Path("/app/hidden/reference/main.rs")


def _ensure_interpreter():
    """Rebuild interpreter from pristine source if needed."""
    if Path(INTERPRETER).exists():
        return
    # Restore from pristine copy and rebuild
    assert PRISTINE_SRC.exists(), "Pristine interpreter source not found"
    subprocess.run(["chmod", "-R", "u+w", "/app/src", "/app/Cargo.toml"], capture_output=True)
    subprocess.run(["cp", str(PRISTINE_SRC), "/app/src/main.rs"], capture_output=True)
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True, text=True, cwd="/app", timeout=600,
    )
    assert result.returncode == 0, f"Rebuild failed:\n{result.stderr[-3000:]}"
    subprocess.run(["chmod", "-R", "a-w", "/app/src", "/app/Cargo.toml"], capture_output=True)


def _run_direct(sam_file: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a .sam program directly with the reference interpreter."""
    _ensure_interpreter()
    return subprocess.run(
        [INTERPRETER, "run", str(sam_file)],
        capture_output=True, text=True, timeout=timeout,
    )


def _run_bootstrap(sam_file: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a .sam program through the bootstrap interpreter."""
    _ensure_interpreter()
    return subprocess.run(
        [INTERPRETER, "run", str(BOOTSTRAP), "--", "run", str(sam_file)],
        capture_output=True, text=True, timeout=timeout,
    )


def test_hidden_arithmetic():
    """Complex arithmetic with factorials and exponentiation through bootstrap."""
    direct = _run_direct(HIDDEN_SAMPLES / "arithmetic_hidden.sam")
    assert direct.returncode == 0, f"Direct run failed:\n{direct.stderr}"

    boot = _run_bootstrap(HIDDEN_SAMPLES / "arithmetic_hidden.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "5! = 120" in lines, f"Missing '5! = 120' in output:\n{boot.stdout}"
    assert "10! = 3628800" in lines, f"Missing '10! = 3628800' in output:\n{boot.stdout}"
    assert "2 ** 16 = 65536" in lines, f"Missing '2 ** 16 = 65536' in output:\n{boot.stdout}"

    assert boot.stdout == direct.stdout, (
        f"Output mismatch:\n  direct: {direct.stdout!r}\n  boot: {boot.stdout!r}"
    )


def test_hidden_all_features():
    """Functions, loops, conditionals, string building, and booleans through bootstrap."""
    direct = _run_direct(HIDDEN_SAMPLES / "all_features.sam")
    assert direct.returncode == 0, f"Direct run failed:\n{direct.stderr}"

    boot = _run_bootstrap(HIDDEN_SAMPLES / "all_features.sam")
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "abs(-7) = 7" in lines, f"Missing 'abs(-7) = 7'"
    assert "countdown: 5, 4, 3, 2, 1" in lines, f"Missing countdown output"
    assert "fib(8) = 21" in lines, f"Missing 'fib(8) = 21'"
    assert "the answer is 42" in lines, f"Missing 'the answer is 42'"
    assert "SamScript v1 is running on WASM!" in lines, f"Missing banner"

    assert boot.stdout == direct.stdout, (
        f"Output mismatch:\n  direct:\n{direct.stdout}\n  boot:\n{boot.stdout}"
    )


def test_hidden_spring_mass():
    """Damped spring-mass simulation — exact f64 parity required."""
    direct = _run_direct(HIDDEN_SAMPLES / "spring_mass.sam", timeout=60)
    assert direct.returncode == 0, f"Direct run failed:\n{direct.stderr}"

    boot = _run_bootstrap(HIDDEN_SAMPLES / "spring_mass.sam", timeout=180)
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "step 100: x = -1.5579217536268157" in lines, (
        f"Missing or wrong step 100:\n{boot.stdout}"
    )
    assert "step 500: x = -0.5723341191714225" in lines, (
        f"Missing or wrong step 500:\n{boot.stdout}"
    )
    assert "step 1000: x = 0.16288221764481955" in lines, (
        f"Missing or wrong step 1000:\n{boot.stdout}"
    )
    assert "zero crossings: 10" in lines, f"Missing zero crossings:\n{boot.stdout}"
    assert "initial energy: 20" in lines, f"Missing initial energy:\n{boot.stdout}"

    assert boot.stdout == direct.stdout, (
        f"Output mismatch — exact f64 parity required:\n"
        f"  direct:\n{direct.stdout}\n  boot:\n{boot.stdout}"
    )


def test_hidden_numerical():
    """Numerical methods — Newton's sqrt, pi, e, harmonic series. Exact f64 parity."""
    direct = _run_direct(HIDDEN_SAMPLES / "numerical.sam", timeout=60)
    assert direct.returncode == 0, f"Direct run failed:\n{direct.stderr}"

    boot = _run_bootstrap(HIDDEN_SAMPLES / "numerical.sam", timeout=180)
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "sqrt(2) = 1.414213562373095" in lines, (
        f"Missing or wrong sqrt(2):\n{boot.stdout}"
    )
    assert "pi (10000 terms) = 3.1414926535900345" in lines, (
        f"Missing or wrong pi:\n{boot.stdout}"
    )
    assert "e (20 terms) = 2.7182818284590455" in lines, (
        f"Missing or wrong e:\n{boot.stdout}"
    )
    assert "H(100) = 5.187377517639621" in lines, (
        f"Missing or wrong harmonic sum:\n{boot.stdout}"
    )

    assert boot.stdout == direct.stdout, (
        f"Output mismatch — exact f64 parity required:\n"
        f"  direct:\n{direct.stdout}\n  boot:\n{boot.stdout}"
    )


def test_hidden_deterministic():
    """Running the same program through bootstrap 3 times gives identical output."""
    outputs = []
    for i in range(3):
        result = _run_bootstrap(HIDDEN_SAMPLES / "all_features.sam")
        assert result.returncode == 0, f"Run {i} failed:\n{result.stderr}"
        outputs.append(result.stdout)

    assert outputs[0] == outputs[1] == outputs[2], (
        f"Non-deterministic bootstrap output across 3 runs"
    )


def test_hidden_error_handling():
    """Division by zero through bootstrap produces non-zero exit code."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sam", dir="/tmp", delete=False
    ) as f:
        f.write('fn main() {\n    let x = 1 / 0\n}\n')
        err_file = f.name

    _ensure_interpreter()
    result = subprocess.run(
        [INTERPRETER, "run", str(BOOTSTRAP), "--", "run", err_file],
        capture_output=True, text=True, timeout=120,
    )
    # The bootstrap should propagate the error — either non-zero exit
    # or error message in output
    error_detected = (
        result.returncode != 0
        or "error" in result.stderr.lower()
        or "error" in result.stdout.lower()
        or "division" in result.stderr.lower()
        or "division" in result.stdout.lower()
    )
    assert error_detected, (
        f"Expected error for division by zero, got rc={result.returncode}\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )

    Path(err_file).unlink(missing_ok=True)


def test_hidden_dynamic_program():
    """A program generated at test time — model cannot anticipate."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sam", dir="/tmp", delete=False
    ) as f:
        f.write(
            'fn main() {\n'
            '    let x = 137\n'
            '    let y = 42\n'
            '    print("${x} + ${y} = ${x + y}")\n'
            '    print("${x} * ${y} = ${x * y}")\n'
            '    let z = x ** 2 + y ** 2\n'
            '    print("${x}^2 + ${y}^2 = ${z}")\n'
            '}\n'
        )
        dyn_file = f.name

    direct = _run_direct(Path(dyn_file))
    assert direct.returncode == 0, f"Direct run failed:\n{direct.stderr}"

    boot = _run_bootstrap(Path(dyn_file))
    assert boot.returncode == 0, f"Bootstrap run failed:\n{boot.stderr}"

    lines = boot.stdout.strip().splitlines()
    assert "137 + 42 = 179" in lines, f"Missing dynamic output:\n{boot.stdout}"
    assert "137 * 42 = 5754" in lines, f"Missing dynamic output:\n{boot.stdout}"
    assert "137^2 + 42^2 = 20533" in lines, f"Missing dynamic output:\n{boot.stdout}"

    assert boot.stdout == direct.stdout, (
        f"Output mismatch on dynamic program:\n"
        f"  direct: {direct.stdout!r}\n  boot: {boot.stdout!r}"
    )

    Path(dyn_file).unlink(missing_ok=True)


def test_hidden_multiple_programs():
    """Multiple different programs all produce correct output through bootstrap."""
    test_files = [
        SAMPLES / "hello.sam",
        SAMPLES / "arithmetic.sam",
        HIDDEN_SAMPLES / "arithmetic_hidden.sam",
    ]

    for sam_file in test_files:
        direct = _run_direct(sam_file)
        assert direct.returncode == 0, f"Direct run of {sam_file.name} failed:\n{direct.stderr}"

        boot = _run_bootstrap(sam_file)
        assert boot.returncode == 0, f"Bootstrap of {sam_file.name} failed:\n{boot.stderr}"

        assert boot.stdout == direct.stdout, (
            f"Output mismatch on {sam_file.name}:\n"
            f"  direct: {direct.stdout!r}\n  boot: {boot.stdout!r}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
