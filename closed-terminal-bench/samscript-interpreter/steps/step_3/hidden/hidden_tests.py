import hashlib
import subprocess
import sys
from pathlib import Path

BINARY = "/app/target/release/samscript"
SAMPLES = Path("/app/step_3/files/samples")
HIDDEN_SAMPLES = Path("/app/step_3/hidden/samples")


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


def _compile_to_wasm(sam_file: Path, out_wasm: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BINARY, "compile", str(sam_file), "-o", out_wasm, "--target", "wasm32-wasi"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_wasm(wasm_file: str, args: list[str] | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ["wasmtime", wasm_file]
    if args:
        cmd.append("--")
        cmd.extend(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_wasm_toolchain(wasm_file: str, subcommand: str, sam_file: str,
                         extra_args: list[str] | None = None,
                         timeout: int = 60) -> subprocess.CompletedProcess:
    cmd = ["wasmtime", "--dir=.", wasm_file, "--", subcommand, sam_file]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd="/app",
    )


def _ensure_bootstrap_wasm() -> str:
    """Build samscript.wasm from the bootstrap source, return path."""
    _build()
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists(), "samscript_bootstrap.sam not found"
    wasm_path = "/tmp/samscript_hidden.wasm"
    comp = _compile_to_wasm(bootstrap, wasm_path, timeout=180)
    assert comp.returncode == 0, f"bootstrap compile failed:\n{comp.stderr}"
    return wasm_path


def test_hidden_wasm_arithmetic_program():
    """Complex arithmetic program correct under wasm interpreter."""
    _build()
    # Direct wasm compilation of the arithmetic program
    result = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_arithmetic.sam", "/tmp/wasm_arith.wasm")
    assert result.returncode == 0, f"wasm compilation failed:\n{result.stderr}"

    wasm_out = _run_wasm("/tmp/wasm_arith.wasm")
    assert wasm_out.returncode == 0, f"wasm execution failed:\n{wasm_out.stderr}"

    # Compare with interpreter output
    interp = _run_interpreted(HIDDEN_SAMPLES / "wasm_arithmetic.sam")
    assert interp.returncode == 0, f"interpreter failed:\n{interp.stderr}"

    assert wasm_out.stdout == interp.stdout, (
        f"wasm/interpreter output mismatch:\n"
        f"  wasm:   {wasm_out.stdout!r}\n"
        f"  interp: {interp.stdout!r}"
    )

    # Verify specific values
    lines = interp.stdout.strip().splitlines()
    assert "5! = 120" in lines
    assert "10! = 3628800" in lines
    assert "2 ** 16 = 65536" in lines


def test_hidden_wasm_compiled_program():
    """Wasm-compiled program produces correct output via bootstrap toolchain."""
    wasm_tc = _ensure_bootstrap_wasm()

    # Use the wasm toolchain to run the arithmetic sample
    result = _run_wasm_toolchain(
        wasm_tc, "run",
        str(SAMPLES / "arithmetic.sam"),
    )
    assert result.returncode == 0, f"wasm toolchain run failed:\n{result.stderr}"

    # Verify output matches interpreter
    interp = _run_interpreted(SAMPLES / "arithmetic.sam")
    assert result.stdout == interp.stdout, (
        f"output mismatch:\n  wasm: {result.stdout!r}\n  interp: {interp.stdout!r}"
    )


def test_hidden_bootstrap_deterministic():
    """Bootstrap produces identical wasm across multiple runs."""
    _build()
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists()

    hashes = []
    for i in range(3):
        out_path = f"/tmp/samscript_det_{i}.wasm"
        comp = _compile_to_wasm(bootstrap, out_path, timeout=180)
        assert comp.returncode == 0, f"compile run {i} failed:\n{comp.stderr}"
        h = hashlib.sha256(Path(out_path).read_bytes()).hexdigest()
        hashes.append(h)

    assert hashes[0] == hashes[1] == hashes[2], (
        f"non-deterministic wasm output:\n  {hashes}"
    )


def test_hidden_wasm_error_handling():
    """Errors in wasm mode produce correct error messages (non-zero exit)."""
    _build()
    # Compile a program that will error at runtime
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sam", dir="/tmp", delete=False
    ) as f:
        f.write('fn main() {\n    let x = 1 / 0\n}\n')
        err_file = f.name

    comp = _compile_to_wasm(Path(err_file), "/tmp/wasm_error.wasm")
    # Compilation might succeed (runtime error), or fail at compile time
    # Either way, running the wasm should produce a non-zero exit
    if comp.returncode == 0:
        result = _run_wasm("/tmp/wasm_error.wasm")
        assert result.returncode != 0, (
            "expected non-zero exit for division by zero in wasm"
        )
    else:
        # Compile-time error is also acceptable
        assert "error" in comp.stderr.lower() or "division" in comp.stderr.lower()

    Path(err_file).unlink(missing_ok=True)


def test_hidden_wasm_all_features():
    """Program using all language features works under wasm."""
    _build()
    result = _compile_to_wasm(HIDDEN_SAMPLES / "wasm_all_features.sam", "/tmp/wasm_all.wasm")
    assert result.returncode == 0, f"wasm compilation failed:\n{result.stderr}"

    wasm_out = _run_wasm("/tmp/wasm_all.wasm")
    assert wasm_out.returncode == 0, f"wasm execution failed:\n{wasm_out.stderr}"

    interp = _run_interpreted(HIDDEN_SAMPLES / "wasm_all_features.sam")
    assert interp.returncode == 0, f"interpreter failed:\n{interp.stderr}"

    assert wasm_out.stdout == interp.stdout, (
        f"wasm/interpreter mismatch:\n"
        f"  wasm:\n{wasm_out.stdout}\n"
        f"  interp:\n{interp.stdout}"
    )

    lines = interp.stdout.strip().splitlines()
    assert "abs(-7) = 7" in lines
    assert "max(3, 9) = 9" in lines
    assert "countdown: 5, 4, 3, 2, 1" in lines
    assert "fib(0) = 0" in lines
    assert "fib(8) = 21" in lines
    assert "the answer is 42" in lines
    assert "SamScript v1 is running on WASM!" in lines


def test_hidden_bootstrap_parity():
    """samscript2.wasm matches samscript.wasm on full test suite."""
    _build()
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists()

    # Stage 1: Rust -> samscript.wasm
    comp1 = _compile_to_wasm(bootstrap, "/tmp/samscript_bp.wasm", timeout=180)
    assert comp1.returncode == 0, f"stage 1 failed:\n{comp1.stderr}"

    # Stage 2: samscript.wasm -> samscript2.wasm
    comp2 = _run_wasm_toolchain(
        "/tmp/samscript_bp.wasm", "compile",
        str(bootstrap),
        extra_args=["-o", "/tmp/samscript2_bp.wasm", "--target", "wasm32-wasi"],
        timeout=180,
    )
    assert comp2.returncode == 0, f"stage 2 failed:\n{comp2.stderr}"

    # Test both on multiple programs
    test_files = [
        SAMPLES / "hello.sam",
        SAMPLES / "arithmetic.sam",
    ]

    for sam_file in test_files:
        out1 = _run_wasm_toolchain(
            "/tmp/samscript_bp.wasm", "run", str(sam_file),
        )
        out2 = _run_wasm_toolchain(
            "/tmp/samscript2_bp.wasm", "run", str(sam_file),
        )

        assert out1.returncode == 0, (
            f"samscript.wasm failed on {sam_file.name}:\n{out1.stderr}"
        )
        assert out2.returncode == 0, (
            f"samscript2.wasm failed on {sam_file.name}:\n{out2.stderr}"
        )
        assert out1.stdout == out2.stdout, (
            f"parity mismatch on {sam_file.name}:\n"
            f"  wasm1: {out1.stdout!r}\n"
            f"  wasm2: {out2.stdout!r}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
