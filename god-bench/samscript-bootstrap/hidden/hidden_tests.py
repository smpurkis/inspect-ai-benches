import subprocess
import tempfile
import tomllib
from pathlib import Path

from generated_oracle import build_error_program, build_program, execute, render

INTERPRETER = "/app/target/release/samscript"
SAMPLES = Path("/app/files/samples")
HIDDEN_SAMPLES = Path("/app/hidden/samples")
BOOTSTRAP = Path("/app/files/samscript_bootstrap.sam")
CONTRACT = Path("/app/files/contract.toml")
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


def test_hidden_task_card_and_read_budget():
    """The strict task stays concise and cannot bulk-read every visible file."""
    task_words = Path("/app/files/TASK.md").read_text(encoding="utf-8").split()
    assert len(task_words) <= 140, f"TASK.md is {len(task_words)} tokens; maximum is 140"
    contract = tomllib.loads(CONTRACT.read_text(encoding="utf-8"))
    corpus_bytes = sum(path.stat().st_size for path in Path("/app/files").rglob("*") if path.is_file())
    assert contract["limits"]["max_file_read_bytes"] < corpus_bytes


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


def test_hidden_generated_runtime_error_class_and_exit():
    """A dynamic error generated from an AST has the oracle's class and exit status."""
    program = build_error_program(0x5A17)
    expected = execute(program)
    assert expected.status == 1 and expected.error_class == "division_by_zero"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sam", dir="/tmp", delete=False) as f:
        f.write(render(program))
        err_file = Path(f.name)
    try:
        result = _run_bootstrap(err_file)
    finally:
        err_file.unlink(missing_ok=True)

    diagnostic = (result.stderr + "\n" + result.stdout).lower()
    assert result.returncode == expected.status, (
        f"division_by_zero must exit {expected.status}, got {result.returncode}: {diagnostic}"
    )
    assert "division" in diagnostic and "zero" in diagnostic, (
        f"wrong runtime error class; expected division_by_zero: {diagnostic!r}"
    )


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


def test_hidden_generated_semantics_and_mutation_dependence():
    """Render/evaluate a seeded AST pair and require exact independent-oracle parity."""
    programs = [build_program(0x51A7C, leaf) for leaf in (6, 7)]
    expected = [execute(program) for program in programs]
    assert all(item.status == 0 for item in expected)
    assert expected[0].stdout != expected[1].stdout, "oracle mutation must be observable"

    solution = BOOTSTRAP.read_text(encoding="utf-8")
    for item in expected:
        for line in item.stdout.splitlines():
            if len(line) >= 12:
                assert line not in solution, f"generated output was canned in bootstrap: {line!r}"

    actual = []
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="sam-ast-") as tmp:
        for index, program in enumerate(programs):
            source = Path(tmp) / f"generated_{index}.sam"
            source.write_text(render(program), encoding="utf-8")
            result = _run_bootstrap(source, timeout=180)
            assert result.returncode == 0, f"generated program {index} failed:\n{result.stderr}"
            assert result.stdout == expected[index].stdout, (
                f"independent-oracle mismatch for generated program {index}:\n"
                f"expected={expected[index].stdout!r}\nactual={result.stdout!r}"
            )
            assert ":BAD:" not in result.stdout, "short-circuited side effect executed"
            actual.append(result.stdout)

    assert actual[0] != actual[1], "changing one AST literal did not change execution"


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
