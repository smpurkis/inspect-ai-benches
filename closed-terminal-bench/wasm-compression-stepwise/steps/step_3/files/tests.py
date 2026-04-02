#!/usr/bin/env python3

import subprocess
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
STEP1_FILES = BASE.parent.parent / "step_1" / "files"
STEP2_RUNNER = BASE.parent.parent / "step_2" / "files" / "run_wasm_codec.sh"
STEP3_RUNNER = BASE / "run_wasm_codec.sh"
STEP3_WASM = BASE / "quiltpress_wasi.wasm"
TEST_FILE = STEP1_FILES / "test.txt"

# Require at least 15% improvement vs Step 2 wasm output.
MAX_IMPROVEMENT_RATIO = 0.85


def run_runner(runner: Path, *args: str) -> None:
    subprocess.run(
        ["bash", str(runner), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_step3_artifacts_present() -> None:
    assert STEP2_RUNNER.exists(), "missing Step 2 runner"
    assert STEP3_RUNNER.exists(), "missing Step 3 run_wasm_codec.sh"
    assert STEP3_WASM.exists(), "missing Step 3 quiltpress_wasi.wasm"


def test_step3_roundtrip_correctness() -> None:
    """Decoded output must equal the original input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "test.step3.qtp"
        restored = tmp / "test.step3.roundtrip.txt"

        run_runner(STEP3_RUNNER, "compress", str(TEST_FILE), str(compressed))
        run_runner(STEP3_RUNNER, "decompress", str(compressed), str(restored))

        original = TEST_FILE.read_bytes()
        decoded = restored.read_bytes()
        assert decoded == original


def test_step3_improvement_over_step2() -> None:
    """Compression ratio must be at most MAX_IMPROVEMENT_RATIO * step 2 size."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        step2_compressed = tmp / "test.step2.qtp"
        step3_compressed = tmp / "test.step3.qtp"

        run_runner(STEP2_RUNNER, "compress", str(TEST_FILE), str(step2_compressed))
        run_runner(STEP3_RUNNER, "compress", str(TEST_FILE), str(step3_compressed))

        original = TEST_FILE.read_bytes()
        step2_encoded = step2_compressed.read_bytes()
        step3_encoded = step3_compressed.read_bytes()

        assert len(step2_encoded) < len(original), "step 2 did not compress"
        assert len(step3_encoded) < len(original), "step 3 did not compress"

        improvement_ratio = len(step3_encoded) / len(step2_encoded)
        assert improvement_ratio <= MAX_IMPROVEMENT_RATIO, (
            f"step3/step2 size ratio {improvement_ratio:.4f} exceeds "
            f"{MAX_IMPROVEMENT_RATIO:.2f}"
        )


def test_step3_runner_depends_on_wasm() -> None:
    """Rename the .wasm file and verify the runner fails, proving it uses wasm."""
    backup = STEP3_WASM.with_suffix(".wasm.bak")
    try:
        STEP3_WASM.rename(backup)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            out = tmp / "should_fail.qtp"
            result = subprocess.run(
                ["bash", str(STEP3_RUNNER), "compress", str(TEST_FILE), str(out)],
                capture_output=True,
            )
            assert result.returncode != 0, (
                "runner succeeded without .wasm file — "
                "it may not actually use the wasm module"
            )
    finally:
        if backup.exists():
            backup.rename(STEP3_WASM)


def test_step3_deterministic_output() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out_a = tmp / "a.step3.qtp"
        out_b = tmp / "b.step3.qtp"

        run_runner(STEP3_RUNNER, "compress", str(TEST_FILE), str(out_a))
        run_runner(STEP3_RUNNER, "compress", str(TEST_FILE), str(out_b))
        assert out_a.read_bytes() == out_b.read_bytes()


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
