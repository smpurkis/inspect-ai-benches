"""Hidden tests for wasm-lz77: additional roundtrip and compression ratio tests."""

import os
import subprocess
import tempfile
import hashlib
import random
import pytest

from lz77_oracle import backreference, decode as oracle_decode, encode_literals

FILES = "/app/files"
RUNNER = os.path.join(FILES, "run_lz77.sh")
WASM = os.path.join(FILES, "lz77.wasm")
WAT = os.path.join(FILES, "lz77.wat")
CORPUS = os.path.join(FILES, "corpus")


def compress(src: str, dst: str, *, timeout=60):
    r = subprocess.run(["bash", RUNNER, "compress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stderr


def decompress(src: str, dst: str, *, timeout=60):
    r = subprocess.run(["bash", RUNNER, "decompress", src, dst],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stderr


def roundtrip(data: bytes, *, timeout=60) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    restored = orig + ".out"
    try:
        rc, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed (rc={rc}):\n{err}"
        rc, err = decompress(compressed, restored, timeout=timeout)
        assert rc == 0, f"decompress failed (rc={rc}):\n{err}"
        return open(restored, "rb").read()
    finally:
        for p in (orig, compressed, restored):
            if os.path.exists(p):
                os.unlink(p)


def get_ratio(data: bytes, *, timeout=60) -> float:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    try:
        rc, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed: {err}"
        return os.path.getsize(compressed) / len(data)
    finally:
        for p in (orig, compressed):
            if os.path.exists(p):
                os.unlink(p)


def encode(data: bytes, *, timeout=60) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        orig = f.name
    compressed = orig + ".lz77"
    try:
        rc, err = compress(orig, compressed, timeout=timeout)
        assert rc == 0, f"compress failed: {err}"
        return open(compressed, "rb").read()
    finally:
        for p in (orig, compressed):
            if os.path.exists(p):
                os.unlink(p)


def decode_with_candidate(stream: bytes, *, timeout=60):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(stream)
        encoded = f.name
    restored = encoded + ".out"
    try:
        rc, err = decompress(encoded, restored, timeout=timeout)
        data = open(restored, "rb").read() if os.path.exists(restored) else None
        return rc, err, data
    finally:
        for path in (encoded, restored):
            if os.path.exists(path):
                os.unlink(path)


def run_compiled_wat(mode: str, data: bytes) -> subprocess.CompletedProcess[bytes]:
    """Compile and execute submitted WAT directly, bypassing any shipped WASM."""
    with tempfile.TemporaryDirectory() as tmpdir:
        module = os.path.join(tmpdir, "submitted.wasm")
        compiled = subprocess.run(
            ["wat2wasm", WAT, "-o", module], capture_output=True, text=True
        )
        assert compiled.returncode == 0, compiled.stderr
        return subprocess.run(
            ["wasmtime", "run", module, "--", mode],
            input=data,
            capture_output=True,
            timeout=60,
        )


# ---------------------------------------------------------------------------
# Correctness: roundtrip on varied data
# ---------------------------------------------------------------------------

def test_roundtrip_null_bytes():
    data = b"\x00" * 500
    assert roundtrip(data) == data


def test_roundtrip_random_like():
    """Data with low entropy (structured but not trivially repetitive)."""
    import struct
    data = b""
    for i in range(1000):
        data += struct.pack("<I", i * 6364136223846793005 & 0xFFFFFFFF)
    result = roundtrip(data)
    assert result == data, f"roundtrip length mismatch: {len(result)} vs {len(data)}"


def test_roundtrip_large_repetitive():
    """Large repetitive data (32KB) roundtrips correctly."""
    data = (b"the quick brown fox jumps over the lazy dog\n") * 750
    result = roundtrip(data, timeout=120)
    assert result == data


def test_roundtrip_test_full_txt():
    path = os.path.join(FILES, "test_full.txt")
    if not os.path.isfile(path):
        pytest.skip("test_full.txt not present")
    data = open(path, "rb").read()
    # Use md5 to compare (faster than byte comparison on large data)
    result = roundtrip(data, timeout=300)
    assert hashlib.md5(result).hexdigest() == hashlib.md5(data).hexdigest(), \
        f"test_full.txt roundtrip failed: {len(result)} vs {len(data)} bytes"


def test_roundtrip_corpus_code():
    path = os.path.join(CORPUS, "code.py")
    if not os.path.isfile(path):
        pytest.skip("corpus/code.py not present")
    data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data


def test_roundtrip_single_byte_repeated():
    path = os.path.join(CORPUS, "single_byte.bin")
    if not os.path.isfile(path):
        data = b"A" * 10000
    else:
        data = open(path, "rb").read()
    result = roundtrip(data)
    assert result == data


def test_roundtrip_seeded_generated_inputs():
    """Exercise random, incompressible, repeated-block, overlap, and window-edge data."""
    rng = random.Random(0x1A77)
    block = rng.randbytes(257)
    cases = {
        "random_bytes": rng.randbytes(1537),
        "incompressible": rng.randbytes(4096),
        "repeated_blocks": block * 16,
        "overlapping_match": b"abc" * 5000,
        "window_boundary": block + rng.randbytes(32768 - len(block)) + block,
    }
    for name, data in cases.items():
        encoded = encode(data, timeout=180)
        assert oracle_decode(encoded) == data, f"{name} oracle decode failed"
        assert roundtrip(data, timeout=180) == data, f"{name} roundtrip failed"


def test_seeded_encoding_is_deterministic():
    rng = random.Random(0xD37E)
    data = rng.randbytes(1024) + (b"deterministic-block" * 300)
    assert encode(data) == encode(data), "compression output changed between runs"


def test_submitted_wat_is_the_executed_codec():
    data = b"actual submitted WAT" * 20
    compressed = run_compiled_wat("compress", data)
    assert compressed.returncode == 0, compressed.stderr.decode(errors="replace")
    assert oracle_decode(compressed.stdout) == data


def test_oracle_streams_cover_overlap_and_32k_boundary():
    overlap = encode_literals(b"A") + backreference(130, 1)
    rc, err, output = decode_with_candidate(overlap)
    assert rc == 0, err
    assert output == b"A" * 131

    rng = random.Random(0x8000)
    prefix = rng.randbytes(32768)
    boundary = encode_literals(prefix) + backreference(3, 32768)
    rc, err, output = decode_with_candidate(boundary)
    assert rc == 0, err
    assert output == prefix + prefix[:3]


@pytest.mark.parametrize(
    "stream",
    [
        b"\x00",
        b"\x7f" + b"x" * 127,
        b"\x80",
        b"\x80\x00",
        backreference(3, 1),
        encode_literals(b"x" * 32769) + backreference(3, 32769),
    ],
    ids=[
        "truncated_literal",
        "short_long_literal",
        "missing_distance",
        "short_distance",
        "distance_before_output",
        "distance_above_32k",
    ],
)
def test_rejects_malformed_streams(stream):
    rc, _, _ = decode_with_candidate(stream)
    assert rc != 0


def test_runner_enforces_input_and_output_ceilings():
    with tempfile.TemporaryDirectory() as tmpdir:
        oversized = os.path.join(tmpdir, "oversized")
        output = os.path.join(tmpdir, "output")
        with open(oversized, "wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        rc, _ = compress(oversized, output)
        assert rc != 0

    expansion = encode_literals(b"Z") + backreference(130, 1) * 258112
    rc, _, output = decode_with_candidate(expansion, timeout=150)
    assert rc != 0
    assert output is None


# ---------------------------------------------------------------------------
# Compression ratio requirements
# ---------------------------------------------------------------------------

def test_ratio_corpus_english():
    path = os.path.join(CORPUS, "english.txt")
    if not os.path.isfile(path):
        pytest.skip("corpus/english.txt not present")
    data = open(path, "rb").read()
    ratio = get_ratio(data)
    assert ratio < 0.5, f"english.txt compression ratio {ratio:.2%} >= 50%"


def test_ratio_single_byte():
    """10KB of single repeated byte should compress to near 0%."""
    data = b"Z" * 10000
    ratio = get_ratio(data)
    assert ratio < 0.1, f"single-byte ratio {ratio:.2%} is surprisingly high (expected < 10%)"


# ---------------------------------------------------------------------------
# WAT source is genuine (not pre-compiled from another language)
# ---------------------------------------------------------------------------

def test_wat_is_text():
    """lz77.wat must be a text file (not binary)."""
    wat_path = os.path.join(FILES, "lz77.wat")
    if not os.path.isfile(wat_path):
        pytest.skip("lz77.wat not found")
    data = open(wat_path, "rb").read(200)
    # WAT files start with (module or whitespace + (module
    text = data.decode("utf-8", errors="replace")
    assert "module" in text, "lz77.wat does not look like a WAT module"
    # Should not be a binary WASM file
    assert not data.startswith(b"\x00asm"), "lz77.wat appears to be a binary WASM file"


def test_wat_uses_standard_instructions():
    """lz77.wat must be valid WAT (recompile to verify)."""
    wat_path = os.path.join(FILES, "lz77.wat")
    if not os.path.isfile(wat_path):
        pytest.skip("lz77.wat not found")
    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
        tmp = f.name
    try:
        r = subprocess.run(["wat2wasm", wat_path, "-o", tmp],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"wat2wasm rejected lz77.wat:\n{r.stderr}"
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def test_runner_has_no_precompiled_execution_path():
    runner = open(RUNNER, encoding="utf-8").read()
    assert "--allow-precompiled" not in runner
    assert "wat2wasm" in runner
