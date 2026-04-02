import subprocess
import sys
from pathlib import Path

BINARY = "/app/target/release/samscript"
SAMPLES = Path("/app/step_3/files/samples")


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
    """Run a samscript.wasm toolchain with a subcommand."""
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


def test_samscript_compiles_to_wasm():
    """Rust toolchain compiles a SamScript source to .wasm."""
    _build()
    result = _compile_to_wasm(SAMPLES / "hello.sam", "/tmp/hello_step3.wasm")
    assert result.returncode == 0, f"wasm compilation failed:\n{result.stderr}"
    assert Path("/tmp/hello_step3.wasm").exists(), "output .wasm file not created"
    assert Path("/tmp/hello_step3.wasm").stat().st_size > 0, "output .wasm file is empty"


def test_wasm_interprets_hello():
    """wasmtime samscript.wasm -- run hello.sam works."""
    _build()
    # First compile the SamScript toolchain (bootstrap source) to wasm
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists(), (
        "samscript_bootstrap.sam not found — you must create a self-hosted toolchain"
    )
    comp = _compile_to_wasm(bootstrap, "/tmp/samscript.wasm", timeout=180)
    assert comp.returncode == 0, f"compiling bootstrap to wasm failed:\n{comp.stderr}"

    # Use the wasm toolchain to interpret hello.sam
    result = _run_wasm_toolchain(
        "/tmp/samscript.wasm", "run",
        str(SAMPLES / "hello.sam"),
    )
    assert result.returncode == 0, f"wasm interpret failed:\n{result.stderr}"
    assert result.stdout.strip() == "hello world", (
        f"expected 'hello world', got: {result.stdout!r}"
    )


def test_wasm_compiles_hello():
    """wasmtime samscript.wasm -- compile hello.sam produces a working wasm."""
    _build()
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists(), "samscript_bootstrap.sam not found"

    comp = _compile_to_wasm(bootstrap, "/tmp/samscript.wasm", timeout=180)
    assert comp.returncode == 0, f"compiling bootstrap to wasm failed:\n{comp.stderr}"

    # Use wasm toolchain to compile hello.sam to wasm
    result = _run_wasm_toolchain(
        "/tmp/samscript.wasm", "compile",
        str(SAMPLES / "hello.sam"),
        extra_args=["-o", "/tmp/hello_from_wasm.wasm", "--target", "wasm32-wasi"],
    )
    assert result.returncode == 0, f"wasm compile failed:\n{result.stderr}"

    # Run the produced wasm
    run_result = _run_wasm("/tmp/hello_from_wasm.wasm")
    assert run_result.returncode == 0, f"compiled wasm failed:\n{run_result.stderr}"
    assert run_result.stdout.strip() == "hello world"


def test_bootstrap_self_compile():
    """samscript.wasm can compile its own source to samscript2.wasm."""
    _build()
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists(), "samscript_bootstrap.sam not found"

    # Compile bootstrap to samscript.wasm
    comp1 = _compile_to_wasm(bootstrap, "/tmp/samscript.wasm", timeout=180)
    assert comp1.returncode == 0, f"stage 1 compile failed:\n{comp1.stderr}"

    # Self-compile: samscript.wasm compiles bootstrap to samscript2.wasm
    comp2 = _run_wasm_toolchain(
        "/tmp/samscript.wasm", "compile",
        str(bootstrap),
        extra_args=["-o", "/tmp/samscript2.wasm", "--target", "wasm32-wasi"],
        timeout=180,
    )
    assert comp2.returncode == 0, f"self-compile failed:\n{comp2.stderr}"
    assert Path("/tmp/samscript2.wasm").exists(), "samscript2.wasm not created"
    assert Path("/tmp/samscript2.wasm").stat().st_size > 0, "samscript2.wasm is empty"


def test_bootstrap_roundtrip_output():
    """samscript2.wasm produces identical output to samscript.wasm."""
    _build()
    bootstrap = Path("/app/samscript_bootstrap.sam")
    assert bootstrap.exists(), "samscript_bootstrap.sam not found"

    # Stage 1: Rust compiler -> samscript.wasm
    comp1 = _compile_to_wasm(bootstrap, "/tmp/samscript_rt.wasm", timeout=180)
    assert comp1.returncode == 0, f"stage 1 failed:\n{comp1.stderr}"

    # Stage 2: samscript.wasm -> samscript2.wasm
    comp2 = _run_wasm_toolchain(
        "/tmp/samscript_rt.wasm", "compile",
        str(bootstrap),
        extra_args=["-o", "/tmp/samscript2_rt.wasm", "--target", "wasm32-wasi"],
        timeout=180,
    )
    assert comp2.returncode == 0, f"stage 2 failed:\n{comp2.stderr}"

    # Both should produce identical output on hello.sam
    out1 = _run_wasm_toolchain(
        "/tmp/samscript_rt.wasm", "run",
        str(SAMPLES / "hello.sam"),
    )
    out2 = _run_wasm_toolchain(
        "/tmp/samscript2_rt.wasm", "run",
        str(SAMPLES / "hello.sam"),
    )
    assert out1.returncode == 0, f"samscript.wasm run failed:\n{out1.stderr}"
    assert out2.returncode == 0, f"samscript2.wasm run failed:\n{out2.stderr}"
    assert out1.stdout == out2.stdout, (
        f"roundtrip output mismatch:\n"
        f"  samscript.wasm:  {out1.stdout!r}\n"
        f"  samscript2.wasm: {out2.stdout!r}"
    )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
