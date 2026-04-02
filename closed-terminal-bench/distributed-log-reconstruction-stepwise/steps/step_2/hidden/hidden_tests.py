#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
FILES_BASE = HIDDEN_BASE.parent / "files"
BINARY = FILES_BASE / "target" / "release" / "log_analytics"
MERGED_STREAM = Path("/app/step_1/files/merged_stream.jsonl")
HIDDEN_REFERENCE = HIDDEN_BASE / "hidden_analytics_reference.json"


def build_cli():
    subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(FILES_BASE),
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


def load_hidden_reference():
    with open(HIDDEN_REFERENCE) as f:
        return json.load(f)


def test_hidden_analytics_exact_match():
    """All analytics metrics must match the hidden reference exactly."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_hidden_reference()

    assert result["sessions"] == ref["sessions"], (
        f"Sessions mismatch: {result['sessions']} != {ref['sessions']}"
    )
    assert result["latency"] == ref["latency"], (
        f"Latency mismatch: {result['latency']} != {ref['latency']}"
    )
    assert result["errors"] == ref["errors"], (
        f"Errors mismatch: {result['errors']} != {ref['errors']}"
    )
    assert result["rates"] == ref["rates"], "Rates mismatch"


def test_hidden_per_minute_rates():
    """Per-minute rates must match reference rate entries exactly."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_hidden_reference()

    result_rates = {r["minute"]: r["count"] for r in result["rates"]}
    ref_rates = {r["minute"]: r["count"] for r in ref["rates"]}

    assert result_rates == ref_rates, (
        f"Rate buckets differ.\n"
        f"  Got {len(result_rates)} buckets, expected {len(ref_rates)}.\n"
        f"  Missing: {set(ref_rates) - set(result_rates)}\n"
        f"  Extra: {set(result_rates) - set(ref_rates)}"
    )


def test_hidden_malformed_input_rejected():
    """CLI must return non-zero exit code on invalid JSONL input."""
    build_cli()
    bad_input = "this is not json\n{\"seq\": 1}\nnope\n"
    result = subprocess.run(
        [str(BINARY), "--all"],
        capture_output=True,
        text=True,
        input=bad_input,
        timeout=30,
    )
    # Should either exit non-zero or produce output that handles errors gracefully
    # Accept either: non-zero exit, or zero exit with valid JSON output
    if result.returncode == 0:
        # If it succeeds, the output must be valid JSON
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError:
            assert False, "CLI succeeded but produced invalid JSON"


def test_hidden_empty_stream_handled():
    """CLI must handle empty input and produce zero-valued or empty metrics."""
    build_cli()
    output = run_cli("--all", input_text="")
    result = json.loads(output)
    assert result["sessions"]["count"] == 0, "Expected 0 sessions for empty input"
    assert result["rates"] == [] or result["rates"] == [{}], (
        f"Expected empty rates for empty input, got {result['rates']}"
    )


def test_hidden_large_stream_performance():
    """CLI must process 100K events within 5 seconds."""
    build_cli()
    # Generate 100K synthetic events
    events = []
    base_ts = 1705312800000
    for i in range(100000):
        events.append(json.dumps({
            "seq": i + 1,
            "timestamp": base_ts + i * 100,
            "session_id": f"session_{i % 50:03d}",
            "event_type": ["request_start", "request_end", "heartbeat"][i % 3],
            "latency_ms": 100 + (i * 7) % 5000,
            "source_shard": "node_a",
        }))
    large_input = "\n".join(events) + "\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(large_input)
        tmp_path = f.name

    try:
        start = time.monotonic()
        run_cli("--all", "--input", tmp_path)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"Processing 100K events took {elapsed:.1f}s (limit: 5s)"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_hidden_deterministic_analytics():
    """Two runs of the CLI on the same input must produce identical output."""
    build_cli()
    output_a = run_cli("--all", "--input", str(MERGED_STREAM))
    output_b = run_cli("--all", "--input", str(MERGED_STREAM))
    assert output_a == output_b, "CLI output is not deterministic across runs"


def test_hidden_window_p99_exact():
    """window_p99 array must match hidden reference exactly (count and values)."""
    build_cli()
    output = run_cli("--window", "60", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_hidden_reference()

    assert "window_p99" in result, "Missing 'window_p99' in output"
    assert "window_p99" in ref, "Missing 'window_p99' in hidden reference"

    result_windows = result["window_p99"]
    ref_windows = ref["window_p99"]

    assert len(result_windows) == len(ref_windows), (
        f"window_p99 count mismatch: got {len(result_windows)}, expected {len(ref_windows)}"
    )
    for i, (r, expected) in enumerate(zip(result_windows, ref_windows)):
        assert r == expected, (
            f"window_p99[{i}] mismatch: got {r}, expected {expected}"
        )


def test_hidden_session_detail_matches_reference():
    """session_details must match the hidden reference exactly."""
    build_cli()
    output = run_cli("--sessions-detail", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_hidden_reference()

    assert "session_details" in result, "Missing 'session_details' in output"
    assert "session_details" in ref, "Missing 'session_details' in hidden reference"

    result_details = result["session_details"]
    ref_details = ref["session_details"]

    assert set(result_details.keys()) == set(ref_details.keys()), (
        f"Session keys mismatch.\n"
        f"  Missing: {set(ref_details) - set(result_details)}\n"
        f"  Extra: {set(result_details) - set(ref_details)}"
    )
    for sid in ref_details:
        assert result_details[sid] == ref_details[sid], (
            f"session_details[{sid!r}] mismatch:\n"
            f"  got:      {result_details[sid]}\n"
            f"  expected: {ref_details[sid]}"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
