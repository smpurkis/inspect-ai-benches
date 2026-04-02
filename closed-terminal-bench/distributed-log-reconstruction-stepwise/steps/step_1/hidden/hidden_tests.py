#!/usr/bin/env python3

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HIDDEN_BASE = Path(__file__).resolve().parent
FILES_BASE = HIDDEN_BASE.parent / "files"
MERGE_SCRIPT = FILES_BASE / "merge_shards.py"
OUTPUT_FILE = FILES_BASE / "merged_stream.jsonl"
REFERENCE_FULL = HIDDEN_BASE / "reference_stream_full.jsonl"

EXPECTED_EVENT_COUNT = 580
EXPECTED_FULL_SHA256 = "534d57fa7528144d1b88b40d43f887b43aeda60a104c03d7bfbf10d0929162ae"


def run_merge():
    subprocess.run(
        [sys.executable, str(MERGE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hidden_full_stream_matches():
    """Complete merged stream must match the hidden full reference exactly."""
    run_merge()
    output = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)
    assert len(output) == len(reference), (
        f"Event count mismatch: got {len(output)}, expected {len(reference)}"
    )
    for i in range(len(reference)):
        assert output[i] == reference[i], (
            f"Mismatch at event {i}:\n"
            f"  output:    {json.dumps(output[i], separators=(',', ':'))}\n"
            f"  reference: {json.dumps(reference[i], separators=(',', ':'))}"
        )


def test_hidden_event_count_exact():
    """Merged stream must have exactly 580 events after deduplication."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    assert len(records) == EXPECTED_EVENT_COUNT, (
        f"Expected {EXPECTED_EVENT_COUNT} events, got {len(records)}"
    )


def test_hidden_timestamp_correction():
    """Timestamps from skewed shards must be corrected properly.

    Verify that events from node_a (offset +300s) and node_d (offset -120s)
    have timestamps within the expected range of the overall stream.
    """
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    reference = load_jsonl(REFERENCE_FULL)

    ref_by_seq = {r["seq"]: r for r in reference}
    for rec in records:
        ref = ref_by_seq.get(rec["seq"])
        assert ref is not None, f"Unexpected seq {rec['seq']}"
        assert rec["timestamp"] == ref["timestamp"], (
            f"Timestamp mismatch for seq {rec['seq']} (shard {rec['source_shard']}): "
            f"got {rec['timestamp']}, expected {ref['timestamp']}"
        )


def test_hidden_dropped_line_recovery():
    """Events from shards with truncated lines must still be recovered
    (from other shards that also contain those events)."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    seqs = {r["seq"] for r in records}
    # These are the truncated sequences in node_c that must be recovered from other shards
    truncated_seqs = {58, 88, 98, 138, 158, 173, 288, 383, 418, 448}
    for seq in truncated_seqs:
        assert seq in seqs, (
            f"Sequence {seq} (truncated in node_c) was not recovered from another shard"
        )


def test_hidden_deterministic_merge():
    """Two runs of the merge script must produce identical output."""
    run_merge()
    content_a = OUTPUT_FILE.read_bytes()

    run_merge()
    content_b = OUTPUT_FILE.read_bytes()

    assert content_a == content_b, "Merge output is not deterministic across runs"


def test_hidden_epoch_normalisation():
    """Events from node_f must have timestamps in milliseconds range (> 1e12), not seconds."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_f_events = [r for r in records if r["source_shard"] == "node_f"]
    assert len(node_f_events) > 0, "No events from node_f found in merged stream"
    for rec in node_f_events:
        assert rec["timestamp"] > 1_000_000_000_000, (
            f"node_f event seq={rec['seq']} has timestamp {rec['timestamp']} "
            f"which looks like seconds, not milliseconds (should be > 1e12)"
        )
        assert rec["timestamp"] < 2_000_000_000_000, (
            f"node_f event seq={rec['seq']} has timestamp {rec['timestamp']} "
            f"which is unexpectedly large"
        )


def test_hidden_base64_decoded_fields():
    """Events from node_c must have valid event_type strings, not raw base64 values."""
    run_merge()
    records = load_jsonl(OUTPUT_FILE)
    node_c_events = [r for r in records if r["source_shard"] == "node_c"]
    assert len(node_c_events) > 0, "No events from node_c found in merged stream"

    valid_event_types = {"request_start", "request_end", "error_500", "error_timeout", "heartbeat"}
    for rec in node_c_events:
        assert rec["event_type"] in valid_event_types, (
            f"node_c event seq={rec['seq']} has invalid event_type: {rec['event_type']!r} "
            f"(should be decoded from base64 if encoded)"
        )


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
