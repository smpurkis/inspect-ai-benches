#!/usr/bin/env python3

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

STEP2_BASE = Path("/app/step_2/files")
BINARY = STEP2_BASE / "target" / "release" / "log_analytics"
MERGED_STREAM = Path("/app/step_1/files/merged_stream.jsonl")
MERGE_SCRIPT = Path("/app/step_1/files/merge_shards.py")
EXPORT_DIR = Path(__file__).resolve().parent

MAGIC = b"LCMP"
VERSION = 1


def build_cli():
    subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(STEP2_BASE),
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )


def run_cli(*args):
    result = subprocess.run(
        [str(BINARY), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"CLI exited with code {result.returncode}\nstderr: {result.stderr}"
    )
    return result.stdout


def run_merge():
    subprocess.run(
        [sys.executable, str(MERGE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_export_mode_produces_artifact():
    """--export flag must produce an output file with more than 10 bytes."""
    build_cli()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        run_cli("--all", "--export", str(export_path), "--input", str(MERGED_STREAM))
        assert export_path.exists(), f"Export file not created at {export_path}"
        assert export_path.stat().st_size > 10, (
            f"Export file too small: {export_path.stat().st_size} bytes"
        )
    finally:
        export_path.unlink(missing_ok=True)


def test_export_magic_bytes():
    """First 4 bytes must be 'LCMP' (0x4C43 4D50), byte 4 must be version 1."""
    build_cli()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        run_cli("--all", "--export", str(export_path), "--input", str(MERGED_STREAM))
        data = export_path.read_bytes()
        assert len(data) >= 5, f"Export too short: {len(data)} bytes"
        assert data[:4] == MAGIC, (
            f"Wrong magic bytes: {data[:4]!r}, expected {MAGIC!r}"
        )
        assert data[4] == VERSION, (
            f"Wrong version byte: {data[4]}, expected {VERSION}"
        )
    finally:
        export_path.unlink(missing_ok=True)


def test_export_lz4_decompressible():
    """Bytes 5 to -8 must be valid LZ4 frame data decompressing to valid JSON analytics."""
    build_cli()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        run_cli("--all", "--export", str(export_path), "--input", str(MERGED_STREAM))
        data = export_path.read_bytes()
        assert len(data) > 13, f"Export too short: {len(data)} bytes"

        # Extract LZ4 compressed region (bytes 5 to -8)
        compressed = data[5:-8]

        # Decompress using lz4.frame
        try:
            import lz4.frame
        except ImportError:
            import subprocess as sp
            sp.run(["pip3", "install", "--break-system-packages", "lz4"], check=True, capture_output=True)
            import lz4.frame

        decompressed = lz4.frame.decompress(compressed)
        analytics = json.loads(decompressed.decode("utf-8"))

        assert "sessions" in analytics, "Decompressed JSON missing 'sessions'"
        assert "latency" in analytics, "Decompressed JSON missing 'latency'"
        assert "errors" in analytics, "Decompressed JSON missing 'errors'"
        assert "rates" in analytics, "Decompressed JSON missing 'rates'"
    finally:
        export_path.unlink(missing_ok=True)


def test_export_json_stdout():
    """stdout during --export run must contain valid JSON analytics."""
    build_cli()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        stdout = run_cli("--all", "--export", str(export_path), "--input", str(MERGED_STREAM))
        analytics = json.loads(stdout)
        assert "sessions" in analytics, "stdout JSON missing 'sessions'"
        assert "latency" in analytics, "stdout JSON missing 'latency'"
        assert "errors" in analytics, "stdout JSON missing 'errors'"
        assert "rates" in analytics, "stdout JSON missing 'rates'"
    finally:
        export_path.unlink(missing_ok=True)


def test_export_deterministic():
    """Two --export runs on the same input must produce byte-identical files (sha256 match)."""
    build_cli()
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / "export_a.bin"
        path_b = Path(tmpdir) / "export_b.bin"

        run_cli("--all", "--export", str(path_a), "--input", str(MERGED_STREAM))
        run_cli("--all", "--export", str(path_b), "--input", str(MERGED_STREAM))

        hash_a = hashlib.sha256(path_a.read_bytes()).hexdigest()
        hash_b = hashlib.sha256(path_b.read_bytes()).hexdigest()
        assert hash_a == hash_b, (
            f"Export not deterministic: sha256 {hash_a} != {hash_b}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
