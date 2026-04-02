import subprocess
import sys
from pathlib import Path

BINARY = "/app/target/release/samscript"
SAMPLES = Path("/app/step_1/files/samples")


def _build():
    """Build the samscript binary in release mode."""
    result = subprocess.run(
        ["cargo", "build", "--release"],
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=600,
    )
    assert result.returncode == 0, f"cargo build failed:\n{result.stderr[-3000:]}"


def _run_interpreted(sam_file: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a .sam file in interpreter mode."""
    return subprocess.run(
        [BINARY, "run", str(sam_file)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_compiled(sam_file: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Compile a .sam file and run the resulting binary."""
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


def test_binary_builds():
    """cargo build --release succeeds."""
    _build()


def test_hello_world_interpreted():
    """samscript run hello.sam prints 'hello world'."""
    _build()
    result = _run_interpreted(SAMPLES / "hello.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    assert result.stdout.strip() == "hello world"


def test_hello_world_compiled():
    """Compiled hello.sam binary prints 'hello world'."""
    _build()
    result = _run_compiled(SAMPLES / "hello.sam")
    assert result.returncode == 0, f"compiled binary failed:\n{result.stderr}"
    assert result.stdout.strip() == "hello world"


def test_arithmetic_operations():
    """Arithmetic expressions produce correct results in interpreter mode."""
    _build()
    result = _run_interpreted(SAMPLES / "arithmetic.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 4, f"expected 4 output lines, got {len(lines)}"
    assert lines[0] == "10 + 3 = 13"
    assert lines[1] == "10 * 3 = 30"
    assert lines[2] == "10 ** 3 = 1000"
    assert lines[3] == "10 % 3 = 1"


def test_string_interpolation():
    """String interpolation with ${} works correctly."""
    _build()
    result = _run_interpreted(SAMPLES / "string_interp.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 4, f"expected 4 lines, got {len(lines)}"
    assert lines[0] == "Welcome to SamScript v1!"
    assert lines[1] == "5 + 7 = 12"
    assert lines[2] == "is 5 < 7? true"
    assert lines[3] == "Hello, SamScript!"


def test_control_flow_loop_break():
    """loop/break/continue work correctly."""
    _build()
    result = _run_interpreted(SAMPLES / "control_flow.sam")
    assert result.returncode == 0, f"interpreter failed:\n{result.stderr}"
    assert result.stdout.strip() == "sum 0..9 = 45"


def test_interpreter_compiler_parity():
    """All sample programs produce identical output in both modes."""
    _build()
    for sam_file in sorted(SAMPLES.glob("*.sam")):
        interp = _run_interpreted(sam_file)
        assert interp.returncode == 0, (
            f"interpreter failed on {sam_file.name}:\n{interp.stderr}"
        )
        compiled = _run_compiled(sam_file)
        assert compiled.returncode == 0, (
            f"compiled binary failed on {sam_file.name}:\n{compiled.stderr}"
        )
        assert interp.stdout == compiled.stdout, (
            f"output mismatch for {sam_file.name}:\n"
            f"  interpreter: {interp.stdout!r}\n"
            f"  compiled:    {compiled.stdout!r}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
