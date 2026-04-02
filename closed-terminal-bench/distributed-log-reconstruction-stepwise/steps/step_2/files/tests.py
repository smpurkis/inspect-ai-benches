#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CARGO_DIR = BASE
BINARY = BASE / "target" / "release" / "log_analytics"
MERGED_STREAM = Path("/app/step_1/files/merged_stream.jsonl")
REFERENCE = BASE / "reference_analytics.json"


def build_cli():
    """Build the Rust CLI in release mode."""
    subprocess.run(
        ["cargo", "build", "--release"],
        cwd=str(CARGO_DIR),
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )


def run_cli(*args):
    """Run the CLI binary with given arguments and return stdout."""
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


def load_reference():
    with open(REFERENCE) as f:
        return json.load(f)


def test_cli_builds():
    """cargo build --release must succeed."""
    build_cli()
    assert BINARY.exists(), f"Expected binary at {BINARY}"


def test_cli_runs_on_stream():
    """CLI must process the merged stream without error."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    assert len(output.strip()) > 0, "CLI produced no output"


def test_session_count_correct():
    """Session count must match reference."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_reference()
    assert result["sessions"]["count"] == ref["sessions"]["count"], (
        f"Session count: got {result['sessions']['count']}, "
        f"expected {ref['sessions']['count']}"
    )


def test_latency_percentiles_correct():
    """Latency p50/p95/p99 must match reference exactly."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_reference()
    for p in ("p50", "p95", "p99"):
        assert result["latency"][p] == ref["latency"][p], (
            f"Latency {p}: got {result['latency'][p]}, expected {ref['latency'][p]}"
        )


def test_error_classification_counts():
    """Error counts by type must match reference."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    ref = load_reference()
    assert result["errors"] == ref["errors"], (
        f"Error counts mismatch:\n  got:      {result['errors']}\n  expected: {ref['errors']}"
    )


def test_output_json_schema_valid():
    """Analytics output must match the expected JSON schema."""
    build_cli()
    output = run_cli("--all", "--input", str(MERGED_STREAM))
    result = json.loads(output)

    assert "sessions" in result, "Missing 'sessions' key"
    assert "count" in result["sessions"], "Missing 'sessions.count'"
    assert isinstance(result["sessions"]["count"], int)

    assert "latency" in result, "Missing 'latency' key"
    for p in ("p50", "p95", "p99"):
        assert p in result["latency"], f"Missing 'latency.{p}'"
        assert isinstance(result["latency"][p], int)

    assert "errors" in result, "Missing 'errors' key"
    assert isinstance(result["errors"], dict)

    assert "rates" in result, "Missing 'rates' key"
    assert isinstance(result["rates"], list)
    for entry in result["rates"]:
        assert "minute" in entry, "Rate entry missing 'minute'"
        assert "count" in entry, "Rate entry missing 'count'"
        assert isinstance(entry["count"], int)


def test_window_p99_flag_works():
    """--window 60 must produce JSON with window_p99 array, each entry with required fields."""
    build_cli()
    output = run_cli("--window", "60", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    assert "window_p99" in result, "Missing 'window_p99' key"
    assert isinstance(result["window_p99"], list), "'window_p99' must be a list"
    assert len(result["window_p99"]) > 0, "'window_p99' array is empty"
    for entry in result["window_p99"]:
        assert "window_start_ms" in entry, "window_p99 entry missing 'window_start_ms'"
        assert "window_end_ms" in entry, "window_p99 entry missing 'window_end_ms'"
        assert "p99_latency_ms" in entry, "window_p99 entry missing 'p99_latency_ms'"
        assert isinstance(entry["window_start_ms"], int)
        assert isinstance(entry["window_end_ms"], int)
        assert isinstance(entry["p99_latency_ms"], int)


def test_sessions_detail_flag_works():
    """--sessions-detail must produce JSON with session_details dict, each value with required fields."""
    build_cli()
    output = run_cli("--sessions-detail", "--input", str(MERGED_STREAM))
    result = json.loads(output)
    assert "session_details" in result, "Missing 'session_details' key"
    assert isinstance(result["session_details"], dict), "'session_details' must be a dict"
    assert len(result["session_details"]) > 0, "'session_details' dict is empty"
    for session_id, stats in result["session_details"].items():
        assert "event_count" in stats, f"session {session_id} missing 'event_count'"
        assert "total_latency_ms" in stats, f"session {session_id} missing 'total_latency_ms'"
        assert "error_count" in stats, f"session {session_id} missing 'error_count'"
        assert "error_rate" in stats, f"session {session_id} missing 'error_rate'"
        assert isinstance(stats["event_count"], int)
        assert isinstance(stats["total_latency_ms"], int)
        assert isinstance(stats["error_count"], int)
        assert isinstance(stats["error_rate"], (int, float))


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
