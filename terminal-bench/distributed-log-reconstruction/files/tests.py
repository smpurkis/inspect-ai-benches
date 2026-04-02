#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
MERGE_SCRIPT = BASE / "merge_shards.py"
OUTPUT_FILE = BASE / "merged_stream.jsonl"
REQUIRED_FIELDS = {"seq", "timestamp", "session_id", "event_type", "latency_ms", "source_shard"}


def run_merge():
    """Run the merge script and return the output file path."""
    subprocess.run(
        [sys.executable, str(MERGE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return OUTPUT_FILE


def load_jsonl(path):
    """Load a JSONL file into a list of dicts."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def test_merge_script_exists():
    """merge_shards.py must exist."""
    assert MERGE_SCRIPT.exists(), f"Expected {MERGE_SCRIPT} to exist"


def test_merge_produces_output():
    """Running merge_shards.py must produce a non-empty output file."""
    run_merge()
    assert OUTPUT_FILE.exists(), f"Expected {OUTPUT_FILE} to exist after merge"
    assert OUTPUT_FILE.stat().st_size > 0, "Output file is empty"


def test_output_strictly_ordered():
    """Output timestamps must be monotonically non-decreasing, with seq as tiebreaker."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    assert len(records) > 0, "No records in output"
    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        assert (curr["timestamp"], curr["seq"]) >= (prev["timestamp"], prev["seq"]), (
            f"Order violation at index {i}: "
            f"({prev['timestamp']}, {prev['seq']}) -> ({curr['timestamp']}, {curr['seq']})"
        )


def test_no_duplicate_sequence_numbers():
    """Each sequence number must appear exactly once in the output."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    seqs = [r["seq"] for r in records]
    assert len(seqs) == len(set(seqs)), (
        f"Found duplicate sequence numbers: {len(seqs)} total, {len(set(seqs))} unique"
    )


def test_output_format_valid_jsonl():
    """Every line must be valid JSON with all required fields of correct types."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    assert len(records) > 0, "No records in output"

    for i, rec in enumerate(records):
        missing = REQUIRED_FIELDS - set(rec.keys())
        assert not missing, f"Record {i} missing fields: {missing}"
        assert isinstance(rec["seq"], int), f"Record {i}: seq must be int"
        assert isinstance(rec["timestamp"], int), f"Record {i}: timestamp must be int"
        assert isinstance(rec["session_id"], str), f"Record {i}: session_id must be str"
        assert isinstance(rec["event_type"], str), f"Record {i}: event_type must be str"
        assert isinstance(rec["latency_ms"], int), f"Record {i}: latency_ms must be int"
        assert isinstance(rec["source_shard"], str), f"Record {i}: source_shard must be str"


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
