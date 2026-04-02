#!/usr/bin/env python3

import hashlib
import importlib.util
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
CODEC_FILE = BASE / "quiltpress_q1.py"
TEST_FILE = BASE / "test.txt"
TEST_SHA256 = "3630fa4a8c4c22e51cf0777e51cdae3ad98ff92749dff236cf023606ff2ff6e2"


def load_codec_module():
    spec = importlib.util.spec_from_file_location("quiltpress_q1", CODEC_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load codec module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CODEC = load_codec_module()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_codec_cli(*args: str) -> None:
    subprocess.run(
        [sys.executable, str(CODEC_FILE), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def expect_value_error(fn) -> None:
    try:
        fn()
        assert False, "expected ValueError"
    except ValueError:
        pass


def parse_blob(blob: bytes) -> tuple[int, int, bytes, bytes]:
    magic, version, method, dict_count_bytes, original_size = struct.unpack_from(
        CODEC.HEADER_FMT, blob, 0
    )
    assert magic == CODEC.MAGIC
    assert version == CODEC.VERSION
    assert method == CODEC.METHOD_CUSTOM

    p = CODEC.HEADER_SIZE
    dict_count = int.from_bytes(blob[p : p + dict_count_bytes], "little")
    p += dict_count_bytes
    dict_size = dict_count * CODEC.CHUNK_LEN
    dictionary_bytes = blob[p : p + dict_size]
    payload = blob[p + dict_size :]

    assert original_size > 0
    assert dict_count_bytes == CODEC.DEFAULT_DICT_COUNT_BYTES
    assert len(dictionary_bytes) == dict_size
    assert len(payload) > 0
    return dict_count_bytes, dict_count, dictionary_bytes, payload


def test_fixture_hash() -> None:
    data = TEST_FILE.read_bytes()
    assert sha256_bytes(data) == TEST_SHA256


def test_roundtrip_and_compression() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        compressed = tmp / "test.qtp"
        restored = tmp / "test.roundtrip.txt"

        run_codec_cli("compress", str(TEST_FILE), str(compressed))
        run_codec_cli("decompress", str(compressed), str(restored))

        original = TEST_FILE.read_bytes()
        decoded = restored.read_bytes()
        encoded = compressed.read_bytes()

        assert decoded == original
        assert len(encoded) < len(original)


def test_byte_level_container_and_command_layout() -> None:
    original = TEST_FILE.read_bytes()
    blob = CODEC.compress_bytes(original)

    dict_count_bytes, dict_count, _, payload = parse_blob(blob)
    assert dict_count > 0

    p = 0
    token_blocks = 0
    literal_blocks = 0
    token_refs = 0

    while p < len(payload):
        assert p + 2 <= len(payload)
        cmd = payload[p]
        count = payload[p + 1]
        p += 2

        assert count > 0
        assert cmd in (0x00, 0x01)

        if cmd == 0x00:
            literal_blocks += 1
            assert p + count <= len(payload)
            p += count
        else:
            token_blocks += 1
            bytes_len = count * dict_count_bytes
            assert p + bytes_len <= len(payload)
            for i in range(count):
                s = p + i * dict_count_bytes
                idx = int.from_bytes(payload[s : s + dict_count_bytes], "little")
                assert idx < dict_count
                token_refs += 1
            p += bytes_len

    assert p == len(payload)
    assert literal_blocks > 0
    assert token_blocks > 0
    assert token_refs > 0
    assert CODEC.decompress_bytes(blob) == original


def test_dict_count_bytes_variants_roundtrip() -> None:
    sample = TEST_FILE.read_bytes()[:8192]
    for n in (1, 2, 3, 4):
        blob = CODEC.compress_bytes(sample, dict_count_bytes=n)
        _, _, _, dict_count_bytes, _ = struct.unpack_from(CODEC.HEADER_FMT, blob, 0)
        assert dict_count_bytes == n
        assert CODEC.decompress_bytes(blob) == sample


def test_reject_invalid_inputs() -> None:
    """Combined: bad dict_count_bytes, bad magic, and unknown payload commands."""
    sample = b"abcde" * 20

    # Invalid dict_count_bytes values
    expect_value_error(lambda: CODEC.compress_bytes(sample, dict_count_bytes=0))
    expect_value_error(lambda: CODEC.compress_bytes(sample, dict_count_bytes=5))

    # Bad magic
    blob = bytearray(CODEC.compress_bytes(TEST_FILE.read_bytes()[:1024]))
    blob[0:4] = b"BAD!"
    expect_value_error(lambda: CODEC.decompress_bytes(bytes(blob)))

    # Unknown payload command byte
    blob2 = bytearray(CODEC.compress_bytes(TEST_FILE.read_bytes()[:4096]))
    _, _, _, dict_count_bytes, _ = struct.unpack_from(CODEC.HEADER_FMT, blob2, 0)
    p = CODEC.HEADER_SIZE
    dict_count = int.from_bytes(blob2[p : p + dict_count_bytes], "little")
    p += dict_count_bytes + dict_count * CODEC.CHUNK_LEN
    assert p + 2 <= len(blob2)
    blob2[p] = 0x7E
    expect_value_error(lambda: CODEC.decompress_bytes(bytes(blob2)))


def test_compression_ratio_below_threshold() -> None:
    """Student codec must actually compress — not just roundtrip."""
    original = TEST_FILE.read_bytes()
    blob = CODEC.compress_bytes(original)
    ratio = len(blob) / len(original)
    assert ratio < 0.80, (
        f"compression ratio {ratio:.3f} — compressed must be <80% of original"
    )


def test_cli_deterministic_output() -> None:
    """Compressing the same input twice via CLI must produce identical output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out_a = tmp / "a.qtp"
        out_b = tmp / "b.qtp"

        run_codec_cli("compress", str(TEST_FILE), str(out_a))
        run_codec_cli("compress", str(TEST_FILE), str(out_b))
        assert out_a.read_bytes() == out_b.read_bytes(), (
            "CLI compression output is not deterministic"
        )


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
