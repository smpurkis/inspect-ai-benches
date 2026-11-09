"""Public examples for the compact LZ77 match-search task."""

import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNNER = BASE / "run_lz77.sh"


def run(mode: str, data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, output = root / "input", root / "output"
        source.write_bytes(data)
        result = subprocess.run(
            ["bash", str(RUNNER), mode, str(source), str(output)],
            capture_output=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        return output.read_bytes()


def test_normal_known_canonical_match() -> None:
    assert run("compress", b"abcabcabc") == b"\x02abc\x83\x02\x00"


def test_edge_empty_stream() -> None:
    assert run("compress", b"") == b""
    assert run("decompress", b"") == b""


def test_overlap_decoder_invariant() -> None:
    assert run("decompress", b"\x00A\xff\x00\x00") == b"A" * 131


def test_deterministic_rerun() -> None:
    data = b"abcdefgh" * 80
    first = run("compress", data)
    assert first == run("compress", data)
    assert run("decompress", first) == data
