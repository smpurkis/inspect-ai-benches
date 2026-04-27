#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
RUNNER = BASE / "run_wasm_codec.sh"
WASM = BASE / "quiltpress_wasi.wasm"
WAT = BASE / "quiltpress_wasi.wat"
TEST_FILE = BASE / "test.txt"
TEST_SHA256 = "c669c58417eb09fe42d5b23af68323432088942b60cf70ac39bc9cf093b83a86"


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


def test_artifacts_present() -> None:
    assert RUNNER.exists(), "missing run_wasm_codec.sh"
    assert WASM.exists(), "missing quiltpress_wasi.wasm"
    assert WAT.exists(), "missing quiltpress_wasi.wat"


def test_wat_compiles() -> None:
    """WAT source must compile with wat2wasm without errors."""
    assert WAT.exists(), "missing quiltpress_wasi.wat"
    with tempfile.TemporaryDirectory() as tmpdir:
        compiled = Path(tmpdir) / "compiled.wasm"
        result = subprocess.run(
            ["wat2wasm", str(WAT), "-o", str(compiled)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"wat2wasm failed:\n{result.stderr}"
        )
        assert compiled.stat().st_size > 100, (
            "compiled WASM is too small to be a real module"
        )


def test_wasm_module_is_valid_binary() -> None:
    """The WASM file must be a real WebAssembly module, not a stub."""
    assert WASM.exists(), "missing quiltpress_wasi.wasm"
    data = WASM.read_bytes()
    assert data[:4] == b"\x00asm", (
        f"quiltpress_wasi.wasm does not start with WASM magic bytes — "
        f"got {data[:4]!r}"
    )
    assert len(data) > 100, (
        f"quiltpress_wasi.wasm is only {len(data)} bytes — too small to be a real module"
    )


def test_roundtrip_correctness() -> None:
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


def test_compression_ratio() -> None:
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


def test_deterministic_output() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out_a = tmp / "a.qtp"
        out_b = tmp / "b.qtp"

        run_runner("compress", str(TEST_FILE), str(out_a))
        run_runner("compress", str(TEST_FILE), str(out_b))
        assert out_a.read_bytes() == out_b.read_bytes()


def test_compressed_has_qpx1_header() -> None:
    """Compressed output must be a valid QPX1 blob with correct header fields."""
    import struct
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "test.qtp"
        run_runner("compress", str(TEST_FILE), str(compressed))
        data = compressed.read_bytes()
        assert len(data) >= 15, f"compressed output too small: {len(data)} bytes"
        magic = data[:4]
        assert magic == b"QPX1", f"bad magic: {magic!r}, expected b'QPX1'"
        version, method, dcb = struct.unpack_from("<BBB", data, 4)
        assert version == 1, f"version={version}, expected 1"
        assert method == 2, f"method={method}, expected 2"
        assert 1 <= dcb <= 4, f"dict_count_bytes={dcb}, expected 1-4"
        original_size = struct.unpack_from("<Q", data, 7)[0]
        expected_size = TEST_FILE.stat().st_size
        assert original_size == expected_size, (
            f"header original_size={original_size}, actual input size={expected_size}"
        )


def test_roundtrip_generated_data() -> None:
    """Roundtrip on programmatically generated data, not from any file on disk."""
    data = b"xyzzy" * 200 + b"alpha" * 150 + bytes(range(64))
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "generated.bin"
        inp.write_bytes(data)
        compressed = tmp / "generated.qtp"
        restored = tmp / "generated.out"
        run_runner("compress", str(inp), str(compressed))
        run_runner("decompress", str(compressed), str(restored))
        assert restored.read_bytes() == data, "roundtrip failed on generated data"


def test_roundtrip_small_varied() -> None:
    """Roundtrip on small and edge-case inputs."""
    cases = [
        b"A",
        b"\x00\xff" * 50,
        b"short string here",
        bytes(range(256)),
    ]
    for i, data in enumerate(cases):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            inp = tmp / f"case_{i}.bin"
            inp.write_bytes(data)
            compressed = tmp / f"case_{i}.qtp"
            restored = tmp / f"case_{i}.out"
            run_runner("compress", str(inp), str(compressed))
            run_runner("decompress", str(compressed), str(restored))
            assert restored.read_bytes() == data, (
                f"roundtrip failed on case {i} ({len(data)} bytes)"
            )


def test_compressed_size_reasonable() -> None:
    """Compressed output must be larger than just a header and smaller than 2x input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "test.qtp"
        run_runner("compress", str(TEST_FILE), str(compressed))
        original_size = TEST_FILE.stat().st_size
        compressed_size = compressed.stat().st_size
        assert compressed_size > 15, (
            f"compressed size {compressed_size} is too small (header alone is 15+ bytes)"
        )
        assert compressed_size < original_size * 2, (
            f"compressed size {compressed_size} is unreasonably large "
            f"(> 2x original {original_size})"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
