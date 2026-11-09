"""Public examples for the compact QuiltPress payload task."""

import importlib.util
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNNER = BASE / "run_wasm_codec.sh"


def reference():
    spec = importlib.util.spec_from_file_location("qpx_reference", BASE / "quiltpress_q1.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_normal_reference_encoding() -> None:
    data = b"abcde" * 10 + b"tail"
    assert run("compress", data) == reference().compress_bytes(data)


def test_edge_empty_input() -> None:
    encoded = run("compress", b"")
    assert encoded == reference().compress_bytes(b"")
    assert run("decompress", encoded) == b""


def test_cross_decoder_invariant() -> None:
    data = bytes(range(64)) + b"literal"
    assert run("decompress", reference().compress_bytes(data)) == data


def test_deterministic_rerun() -> None:
    data = b"quilt" * 12 + bytes(range(32))
    first = run("compress", data)
    assert first == run("compress", data)
    assert reference().decompress_bytes(first) == data
