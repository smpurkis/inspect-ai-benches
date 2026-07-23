#!/usr/bin/env python3
"""Public smoke and cross-codec tests for QuiltPress-Q1."""

import importlib.util
import subprocess
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
RUNNER = BASE / "run_wasm_codec.sh"
WASM = BASE / "quiltpress_wasi.wasm"
WAT = BASE / "quiltpress_wasi.wat"
REFERENCE = BASE / "quiltpress_q1.py"
TEST_FILE = BASE / "test.txt"


def load_reference():
    spec = importlib.util.spec_from_file_location("quiltpress_q1", REFERENCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["bash", str(RUNNER), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"runner failed ({result.returncode})\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result


def test_trusted_artifacts_present_and_wat_compiles() -> None:
    assert RUNNER.is_file()
    assert WAT.is_file()
    assert WASM.read_bytes().startswith(b"\x00asm")
    with tempfile.TemporaryDirectory() as tmpdir:
        compiled = Path(tmpdir) / "compiled.wasm"
        result = subprocess.run(
            ["wat2wasm", str(WAT), "-o", str(compiled)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert compiled.stat().st_size > 100


def test_wasm_roundtrip_ratio_and_determinism() -> None:
    original = TEST_FILE.read_bytes()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        first = tmp / "first.qpx"
        second = tmp / "second.qpx"
        restored = tmp / "restored"
        run_runner("compress", str(TEST_FILE), str(first))
        run_runner("compress", str(TEST_FILE), str(second))
        run_runner("decompress", str(first), str(restored))
        assert restored.read_bytes() == original
        assert first.read_bytes() == second.read_bytes()
        assert first.stat().st_size < len(original)


def test_public_wasm_compress_python_decompress() -> None:
    reference = load_reference()
    data = b"public cross codec alpha" * 80 + bytes(range(64))
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        source = tmp / "source"
        encoded = tmp / "encoded.qpx"
        source.write_bytes(data)
        run_runner("compress", str(source), str(encoded))
        assert reference.decompress_bytes(encoded.read_bytes()) == data


def test_public_python_compress_wasm_decompress() -> None:
    reference = load_reference()
    data = b"abcde" * 100 + b"literal tail"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        encoded = tmp / "python.qpx"
        restored = tmp / "restored"
        encoded.write_bytes(reference.compress_bytes(data))
        run_runner("decompress", str(encoded), str(restored))
        assert restored.read_bytes() == data


def test_visible_reference_cli_smoke() -> None:
    data = b"reference CLI" * 40
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        source = tmp / "source"
        encoded = tmp / "encoded"
        restored = tmp / "restored"
        source.write_bytes(data)
        for command in (
            ["python3", str(REFERENCE), "compress", str(source), str(encoded)],
            ["python3", str(REFERENCE), "decompress", str(encoded), str(restored)],
        ):
            result = subprocess.run(command, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
        assert restored.read_bytes() == data


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", "-q", __file__]))
