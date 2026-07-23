"""Smoke tests for the public LZ77-T1 contract."""

import os
import subprocess
import tempfile

FILES = "/app/files"
RUNNER = os.path.join(FILES, "run_lz77.sh")
WAT = os.path.join(FILES, "lz77.wat")
WASM = os.path.join(FILES, "lz77.wasm")
CORPUS = os.path.join(FILES, "corpus")


def compress(src: str, dst: str, *, timeout=30):
    r = subprocess.run(["bash", RUNNER, "compress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def decompress(src: str, dst: str, *, timeout=30):
    r = subprocess.run(["bash", RUNNER, "decompress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def roundtrip(data: bytes, *, timeout=30) -> bytes:
    """Compress then decompress data; return decompressed bytes."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    restored = orig + ".out"
    try:
        rc, out, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed (rc={rc}):\n{err}"
        assert os.path.isfile(compressed), "compress produced no output file"

        rc, out, err = decompress(compressed, restored, timeout=timeout)
        assert rc == 0, f"decompress failed (rc={rc}):\n{err}"
        assert os.path.isfile(restored), "decompress produced no output file"

        return open(restored, "rb").read()
    finally:
        for p in (orig, compressed, restored):
            if os.path.exists(p):
                os.unlink(p)


# ---------------------------------------------------------------------------
# Artifact checks
# ---------------------------------------------------------------------------

def test_trusted_artifacts_present():
    assert os.path.isfile(WAT), f"{WAT} not found"
    assert os.path.isfile(WASM), f"{WASM} not found"
    assert os.path.isfile(RUNNER), "run_lz77.sh not found"
    assert os.access(RUNNER, os.X_OK), "run_lz77.sh not executable"


def test_wasm_compiles_from_wat():
    """WAT source can be compiled by wat2wasm."""
    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
        tmp_wasm = f.name
    try:
        r = subprocess.run(["wat2wasm", WAT, "-o", tmp_wasm], capture_output=True, text=True)
        assert r.returncode == 0, f"wat2wasm failed:\n{r.stderr}"
        assert os.path.getsize(tmp_wasm) > 0
    finally:
        if os.path.exists(tmp_wasm):
            os.unlink(tmp_wasm)


def test_basic_roundtrips():
    for data in (b"", b"Hello, World!", bytes(range(256)), b"abc" * 400):
        assert roundtrip(data) == data


# ---------------------------------------------------------------------------
# Compression ratio
# ---------------------------------------------------------------------------

def compression_ratio(data: bytes) -> float:
    """Return ratio = compressed_size / original_size (lower is better)."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    try:
        rc, _, err = compress(orig, compressed)
        assert rc == 0, f"compress failed: {err}"
        return os.path.getsize(compressed) / len(data)
    finally:
        for p in (orig, compressed):
            if os.path.exists(p):
                os.unlink(p)


def test_repetitive_data_compresses_deterministically():
    data = b"abcdefgh" * 1000
    assert compression_ratio(data) < 0.5

    with tempfile.TemporaryDirectory() as tmpdir:
        source = os.path.join(tmpdir, "input")
        first = os.path.join(tmpdir, "first")
        second = os.path.join(tmpdir, "second")
        with open(source, "wb") as stream:
            stream.write(data)
        assert compress(source, first)[0] == 0
        assert compress(source, second)[0] == 0
        assert open(first, "rb").read() == open(second, "rb").read()
