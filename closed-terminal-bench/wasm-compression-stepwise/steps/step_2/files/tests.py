#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
STEP1_FILES = BASE.parent.parent / "step_1" / "files"
RUNNER = BASE / "run_wasm_codec.sh"
WASM = BASE / "quiltpress_wasi.wasm"
WAT = BASE / "quiltpress_wasi.wat"
TEST_FILE = STEP1_FILES / "test.txt"
TEST_SHA256 = "3630fa4a8c4c22e51cf0777e51cdae3ad98ff92749dff236cf023606ff2ff6e2"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_runner(*args: str) -> None:
    cmd = ["bash", str(RUNNER), *args]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            "runner command failed\n"
            f"cmd: {cmd}\n"
            f"returncode: {exc.returncode}\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        ) from exc


def test_step2_artifacts_present() -> None:
    assert RUNNER.exists(), "missing run_wasm_codec.sh"
    assert WASM.exists(), "missing quiltpress_wasi.wasm"
    assert WAT.exists(), "missing quiltpress_wasi.wat"


def test_step2_wat_compiles_to_shipped_wasm() -> None:
    """Recompile the WAT source and verify it matches the shipped WASM binary."""
    assert WAT.exists(), "missing quiltpress_wasi.wat"
    assert WASM.exists(), "missing quiltpress_wasi.wasm"
    with tempfile.TemporaryDirectory() as tmpdir:
        recompiled = Path(tmpdir) / "recompiled.wasm"
        subprocess.run(
            ["wat2wasm", str(WAT), "-o", str(recompiled)],
            check=True,
            capture_output=True,
        )
        assert recompiled.read_bytes() == WASM.read_bytes(), (
            "recompiled WAT does not match shipped WASM — "
            "either the WAT source is stale or the WASM was not compiled from it"
        )


def test_step2_wasm_module_is_valid_binary() -> None:
    """The shipped WASM file must be a real WebAssembly module, not a stub."""
    assert WASM.exists(), "missing quiltpress_wasi.wasm"
    data = WASM.read_bytes()
    assert data[:4] == b"\x00asm", (
        f"quiltpress_wasi.wasm does not start with WASM magic bytes — "
        f"got {data[:4]!r}"
    )
    assert len(data) > 100, (
        f"quiltpress_wasi.wasm is only {len(data)} bytes — too small to be a real module"
    )


def test_step2_roundtrip_correctness() -> None:
    """Decoded output must equal the original input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "test.qtp"
        restored = tmp / "test.roundtrip.txt"

        run_runner("compress", str(TEST_FILE), str(compressed))
        run_runner("decompress", str(compressed), str(restored))

        original = TEST_FILE.read_bytes()
        decoded = restored.read_bytes()
        assert decoded == original


def test_step2_compression_ratio() -> None:
    """Compressed size must be less than the original."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "test.qtp"

        run_runner("compress", str(TEST_FILE), str(compressed))

        original = TEST_FILE.read_bytes()
        encoded = compressed.read_bytes()
        assert len(encoded) < len(original), (
            f"compressed size {len(encoded)} >= original size {len(original)}"
        )


def test_step2_deterministic_output() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out_a = tmp / "a.qtp"
        out_b = tmp / "b.qtp"

        run_runner("compress", str(TEST_FILE), str(out_a))
        run_runner("compress", str(TEST_FILE), str(out_b))
        assert out_a.read_bytes() == out_b.read_bytes()


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
