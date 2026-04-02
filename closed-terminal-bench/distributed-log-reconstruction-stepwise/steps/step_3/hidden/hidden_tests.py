#!/usr/bin/env python3

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
STEP2_BASE = Path("/app/step_2/files")
BINARY = STEP2_BASE / "target" / "release" / "log_analytics"
MERGED_STREAM = Path("/app/step_1/files/merged_stream.jsonl")
MERGE_SCRIPT = Path("/app/step_1/files/merge_shards.py")
HIDDEN_ANALYTICS_REF = HIDDEN_BASE.parent.parent / "step_2" / "hidden" / "hidden_analytics_reference.json"

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


def run_cli(*args, input_text=None):
    result = subprocess.run(
        [str(BINARY), *args],
        capture_output=True,
        text=True,
        input=input_text,
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


def _try_import_lz4():
    try:
        import lz4.frame
        return lz4.frame
    except ImportError:
        subprocess.run(
            ["pip3", "install", "--break-system-packages", "lz4"],
            check=True, capture_output=True
        )
        import lz4.frame
        return lz4.frame


def test_hidden_heap_under_10mb():
    """Export processing heap RSS must stay under 10240 KB (10 MB) for any stream size."""
    build_cli()

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)

    try:
        result = subprocess.run(
            [
                "/usr/bin/time", "-v",
                str(BINARY), "--all", "--export", str(export_path),
                "--input", str(MERGED_STREAM),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"CLI failed during heap test: {result.stderr}"
        )
        # /usr/bin/time -v outputs to stderr; parse "Maximum resident set size"
        stderr = result.stderr
        rss_kb = None
        for line in stderr.splitlines():
            if "Maximum resident set size" in line:
                # Format: "\tMaximum resident set size (kbytes): 12345"
                rss_kb = int(line.split(":")[-1].strip())
                break
        assert rss_kb is not None, (
            f"Could not parse RSS from /usr/bin/time output.\nstderr: {stderr}"
        )
        assert rss_kb < 10240, (
            f"Heap RSS {rss_kb} KB exceeds 10240 KB (10 MB) limit"
        )
    finally:
        export_path.unlink(missing_ok=True)


def test_hidden_checksum_valid():
    """Last 8 bytes of export must be a valid xxHash64 checksum of bytes[5:-8] (little-endian u64)."""
    build_cli()
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        run_cli("--all", "--export", str(export_path), "--input", str(MERGED_STREAM))
        data = export_path.read_bytes()
        assert len(data) > 13, f"Export too short: {len(data)} bytes"

        # Extract stored checksum (last 8 bytes, little-endian u64)
        stored_checksum = struct.unpack("<Q", data[-8:])[0]

        # Compute expected checksum using xxhash64 of bytes[5:-8]
        compressed_payload = data[5:-8]
        try:
            import xxhash
            computed_checksum = xxhash.xxh64(compressed_payload).intdigest()
        except ImportError:
            # Try xxhash-python
            subprocess.run(
                ["pip3", "install", "--break-system-packages", "xxhash"],
                check=True, capture_output=True
            )
            import xxhash
            computed_checksum = xxhash.xxh64(compressed_payload).intdigest()

        assert stored_checksum == computed_checksum, (
            f"xxHash64 checksum mismatch: stored 0x{stored_checksum:016x}, "
            f"computed 0x{computed_checksum:016x}"
        )
    finally:
        export_path.unlink(missing_ok=True)


def test_hidden_streaming_identical_to_batch():
    """Decompressed export JSON must match --all batch output exactly."""
    build_cli()
    lz4 = _try_import_lz4()

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        # Run export (also prints JSON to stdout)
        export_stdout = run_cli(
            "--all", "--export", str(export_path), "--input", str(MERGED_STREAM)
        )
        # Run batch (plain --all)
        batch_stdout = run_cli("--all", "--input", str(MERGED_STREAM))

        # Compare JSON outputs
        export_analytics = json.loads(export_stdout)
        batch_analytics = json.loads(batch_stdout)
        assert export_analytics == batch_analytics, (
            "Export stdout JSON differs from batch --all output"
        )

        # Also verify the compressed payload decodes to matching JSON
        data = export_path.read_bytes()
        compressed = data[5:-8]
        decompressed = lz4.decompress(compressed)
        compressed_analytics = json.loads(decompressed.decode("utf-8"))
        assert compressed_analytics == batch_analytics, (
            "LZ4-decompressed export JSON differs from batch --all output"
        )
    finally:
        export_path.unlink(missing_ok=True)


def test_hidden_export_roundtrip():
    """Two separate --export runs must produce byte-identical files."""
    build_cli()
    with tempfile.TemporaryDirectory() as tmpdir:
        path_1 = Path(tmpdir) / "first.bin"
        path_2 = Path(tmpdir) / "second.bin"

        run_cli("--all", "--export", str(path_1), "--input", str(MERGED_STREAM))
        run_cli("--all", "--export", str(path_2), "--input", str(MERGED_STREAM))

        assert path_1.read_bytes() == path_2.read_bytes(), (
            "Two export runs produced different bytes (not deterministic)"
        )


def test_hidden_pipeline_fresh_run():
    """Delete merged_stream.jsonl, re-run merge, re-run export; verify sessions match reference."""
    build_cli()

    if MERGED_STREAM.exists():
        MERGED_STREAM.unlink()

    run_merge()
    assert MERGED_STREAM.exists(), "Merge did not produce merged_stream.jsonl"

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        export_path = Path(f.name)
    try:
        stdout = run_cli(
            "--all", "--export", str(export_path), "--input", str(MERGED_STREAM)
        )
        analytics = json.loads(stdout)
        ref = json.load(open(HIDDEN_ANALYTICS_REF))

        assert analytics["sessions"] == ref["sessions"], (
            f"Sessions mismatch after fresh pipeline run: "
            f"{analytics['sessions']} != {ref['sessions']}"
        )
        assert analytics["latency"] == ref["latency"], (
            f"Latency mismatch after fresh pipeline run"
        )
        assert analytics["errors"] == ref["errors"], (
            f"Errors mismatch after fresh pipeline run"
        )
    finally:
        export_path.unlink(missing_ok=True)


def test_hidden_second_pass_identical():
    """Two full pipeline passes (merge + export) must produce byte-identical results."""
    build_cli()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Pass 1
        run_merge()
        export_1 = Path(tmpdir) / "pass1.bin"
        stdout_1 = run_cli(
            "--all", "--export", str(export_1), "--input", str(MERGED_STREAM)
        )
        stream_1 = MERGED_STREAM.read_bytes()

        # Pass 2
        run_merge()
        export_2 = Path(tmpdir) / "pass2.bin"
        stdout_2 = run_cli(
            "--all", "--export", str(export_2), "--input", str(MERGED_STREAM)
        )
        stream_2 = MERGED_STREAM.read_bytes()

        assert stream_1 == stream_2, "Merged streams differ between pipeline passes"
        assert stdout_1 == stdout_2, "JSON stdout differs between pipeline passes"
        assert export_1.read_bytes() == export_2.read_bytes(), (
            "Export binaries differ between pipeline passes"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
